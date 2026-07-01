"""Blinkly — a friendly eye-break reminder.

Shows a periodic "look away" overlay (the 20-20-20 rule), lives in the system
tray, and is configured from a small local web page.  This module wires those
pieces together and is written to degrade gracefully when an optional Linux
dependency (tkinter, the AppIndicator tray backend, a sound player, …) is
missing, printing an actionable message instead of crashing.
"""

import sys
import math
import time
import socket
import platform
import threading
import traceback
import webbrowser
from pathlib import Path

# ----- Optional GUI toolkits (import defensively) -----------------------------
try:
    import tkinter as tk
except Exception as _tk_err:  # python3-tk not installed
    tk = None
    _TK_IMPORT_ERROR = _tk_err

try:
    import pystray
except Exception as _ps_err:  # e.g. AppIndicator typelib missing on GNOME
    pystray = None
    _PYSTRAY_IMPORT_ERROR = _ps_err

from PIL import Image, ImageDraw, ImageFont

try:
    from screeninfo import get_monitors as _get_monitors
except Exception as _si_err:
    _get_monitors = None
    _SCREENINFO_IMPORT_ERROR = _si_err

# ----- Web settings panel -----------------------------------------------------
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydantic import BaseModel, Field

# ----- Local helpers ----------------------------------------------------------
from appdirs import user_config_dir
from helpers import autostart, desktop_shortcut, notify
from helpers import sound as sound_helper
from helpers import idle as idle_helper
from helpers import fullscreen as fullscreen_helper
from helpers.stats import BreakStats


# ============================================================
# CONFIGURATION & MODEL
# ============================================================

def resource_path(relative_path):
    """Get absolute path to a bundled resource (works under PyInstaller too)."""
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(__file__).parent
    return base_path / relative_path


APP_NAME = "Blinkly"
CONFIG_DIR = Path(user_config_dir(APP_NAME))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = CONFIG_DIR / "blinkly_settings.json"
STATS_FILE = CONFIG_DIR / "blinkly_stats.json"

STATIC_DIR = resource_path("static")
SOUND_FILE = resource_path("assets/pan2.mp3")
ASSETS_DIR = resource_path("assets")

HOST = "127.0.0.1"
PORT = 8000
SETTINGS_URL = f"http://{HOST}:{PORT}/"

LOOK_AWAY_MESSAGE = "Look ~20 ft (6 m) away and blink softly"
SNOOZE_SECONDS = 300
FULLSCREEN_RETRY_SECONDS = 60

PRESETS = {
    # name: (interval minutes, duration seconds)
    "20-20-20": (20, 20),
    "eyecare-45": (45, 30),
    "pomodoro": (25, 60),
}


class SettingsModel(BaseModel):
    break_interval: int = Field(20, description="Minutes between breaks", ge=1, le=180)
    break_duration: int = Field(20, description="Break length in seconds", ge=5, le=600)
    pause_blinkly: bool = Field(False, description="Pause Blinkly")

    # Sound
    sound_enabled: bool = Field(False, description="Play a sound when a break starts")
    volume: int = Field(80, description="Sound volume", ge=0, le=100)

    # Notifications
    notify_before: int = Field(15, description="Warn N seconds before a break (0 = off)", ge=0, le=120)

    # Behaviour
    strict_mode: bool = Field(False, description="Breaks cannot be skipped")
    skip_on_fullscreen: bool = Field(True, description="Defer breaks during fullscreen apps")
    idle_reset: bool = Field(True, description="Skip breaks while already idle")
    idle_threshold: int = Field(120, description="Idle seconds counted as away", ge=30, le=1800)

    # Micro-breaks (gentle notification nudges between full breaks)
    micro_breaks_enabled: bool = Field(False, description="Enable micro-break nudges")
    micro_break_interval: int = Field(5, description="Minutes between micro-breaks", ge=1, le=60)
    micro_break_duration: int = Field(20, description="Suggested micro-break seconds", ge=5, le=120)

    # Preset ("custom" keeps the manual interval/duration values)
    preset: str = Field("custom", description="Preset name or 'custom'")

    # Startup
    autostart_enabled: bool = Field(False, description="Start automatically on login")
    start_minimized: bool = Field(False, description="Do not open settings on launch")


def apply_preset(model: SettingsModel) -> SettingsModel:
    """If a known preset is selected, force its interval/duration."""
    preset = PRESETS.get(model.preset)
    if preset:
        interval, duration = preset
        model = model.model_copy(update={"break_interval": interval, "break_duration": duration})
    return model


class SettingsManager:
    def __init__(self, path: Path, default: SettingsModel):
        self.path = path
        self._data = default
        self._lock = threading.Lock()

    def load(self) -> SettingsModel:
        if self.path.exists():
            try:
                self._data = SettingsModel.model_validate_json(self.path.read_text())
            except Exception as e:
                print(f"[WARN] Failed to load settings: {e}")
        return self._data

    def save(self, model: SettingsModel):
        with self._lock:
            self.path.write_text(model.model_dump_json(indent=2))
            self._data = model

    @property
    def current(self) -> SettingsModel:
        return self._data


settings_manager = SettingsManager(SETTINGS_FILE, SettingsModel())
settings = settings_manager.load()
stats = BreakStats(STATS_FILE)


# ============================================================
# FASTAPI SETTINGS PANEL
# ============================================================

app = FastAPI()


@app.get("/api/settings")
def get_settings():
    return settings_manager.current.model_dump()


@app.get("/api/stats")
def get_stats():
    return stats.summary()


@app.get("/api/capabilities")
def get_capabilities():
    """Report which optional features are usable, for the settings UI."""
    return {
        "sound": sound_helper.available(),
        "notifications": notify.available(),
        "idle": idle_helper.available(),
        "fullscreen": fullscreen_helper.available(),
        "tray": pystray is not None,
        "overlay": tk is not None,
    }


@app.post("/api/save", response_class=JSONResponse)
def save_settings_api(model: SettingsModel):
    model = apply_preset(model)
    settings_manager.save(model)
    # Keep the on-disk autostart entry in sync with the toggle.
    autostart.sync_autostart(model.autostart_enabled, app_name=APP_NAME)
    return {"status": "ok", "message": "Settings saved successfully"}


# Serve the static frontend (mounted last so /api/* wins).
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="settings")


def start_web_ui():
    """Run the FastAPI server (blocking); intended to run in a daemon thread."""
    try:
        uvicorn.run(app, host=HOST, port=PORT, log_level="error", log_config=None)
    except Exception:
        try:
            with open(CONFIG_DIR / "blinkly_error.log", "w", encoding="utf-8") as f:
                f.write("FastAPI startup failed:\n")
                f.write(traceback.format_exc())
        except Exception:
            pass


def open_settings_page_when_ready(timeout=20):
    """Wait until the server is reachable, then open the settings page."""
    def _wait_and_open():
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection((HOST, PORT), timeout=1):
                    open_settings_app_mode()
                    return
            except OSError:
                time.sleep(0.5)
        open_settings_app_mode()

    threading.Thread(target=_wait_and_open, daemon=True).start()


def open_settings_app_mode():
    """Open the settings page, preferring an app-mode browser window."""
    system = platform.system()
    try:
        if system == "Windows":
            candidates = [
                (r"C:\Program Files\Google\Chrome\Application\chrome.exe", ["--app=" + SETTINGS_URL, "--window-size=900,700"]),
                (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", ["--app=" + SETTINGS_URL, "--window-size=900,700"]),
                (r"C:\Program Files\Mozilla Firefox\firefox.exe", ["-kiosk", SETTINGS_URL]),
            ]
            import subprocess
            for path, args in candidates:
                if Path(path).exists():
                    subprocess.Popen([path, *args])
                    return
            webbrowser.open(SETTINGS_URL)
        elif system == "Linux":
            import shutil
            import subprocess
            for cmd, args in (
                ("google-chrome", ["--app=" + SETTINGS_URL, "--window-size=900,700"]),
                ("chromium-browser", ["--app=" + SETTINGS_URL, "--window-size=900,700"]),
                ("chromium", ["--app=" + SETTINGS_URL, "--window-size=900,700"]),
            ):
                if shutil.which(cmd):
                    subprocess.Popen([cmd, *args])
                    return
            webbrowser.open(SETTINGS_URL)
        elif system == "Darwin":
            import subprocess
            chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            if Path(chrome).exists():
                subprocess.Popen([chrome, "--app=" + SETTINGS_URL, "--window-size=900,700"])
            else:
                subprocess.Popen(["open", SETTINGS_URL])
        else:
            webbrowser.open(SETTINGS_URL)
    except Exception as e:
        print(f"[blinkly] Could not open settings window: {e}")
        try:
            webbrowser.open(SETTINGS_URL)
        except Exception:
            pass


# ============================================================
# TRAY ICON
# ============================================================

def create_eye_icon(minutes_left, paused=False):
    width, height = 64, 64
    if platform.system() == "Windows":
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    else:
        img = Image.new("RGB", (width, height), "black")

    draw = ImageDraw.Draw(img)
    if paused:
        draw.ellipse([8, 16, 56, 48], outline="white", width=4)
        draw.ellipse([26, 26, 38, 38], fill="white")
        draw.line([0, 0, width, height], fill="white", width=4)
        return img

    font_size = 56
    if minutes_left >= 100:
        font_size = 38
    try:
        font = ImageFont.load_default(font_size)
    except TypeError:
        # Pillow < 10.1 doesn't accept a size argument.
        font = ImageFont.load_default()

    text = str(minutes_left)
    x = 16 if len(text) == 1 else -2
    draw.text((x, (64 - font_size) / 2 - 6), text, fill="white", font=font)
    return img


# ============================================================
# BREAK OVERLAY
# ============================================================

class _FakeMonitor:
    def __init__(self, width, height, x=0, y=0):
        self.width, self.height, self.x, self.y = width, height, x, y


def _safe_get_monitors():
    if _get_monitors is not None:
        try:
            monitors = list(_get_monitors())
            if monitors:
                return monitors
        except Exception as e:
            print(f"[blinkly] Could not enumerate monitors: {e}")
    return None  # signal "unknown" -> caller uses a single fullscreen window


def show_break_overlay(duration, message, allow_skip=True, allow_snooze=True):
    """Darken every screen for ``duration`` seconds.

    Returns one of ``"completed"``, ``"skipped"`` or ``"snoozed"``.  When tkinter
    is unavailable the overlay is skipped (we just wait) so the rest of the app
    keeps working.
    """
    if tk is None:
        print("[blinkly] tkinter not available; install 'python3-tk' to enable "
              "the break overlay. Waiting without a visual break.")
        time.sleep(duration)
        return "completed"

    state = {"result": "completed", "done": False}
    root = tk.Tk()
    root.withdraw()

    monitors = _safe_get_monitors()
    windows = []

    def make_window(geometry=None, fullscreen=False):
        w = tk.Toplevel(root)
        w.configure(bg="black")
        w.attributes("-topmost", True)
        try:
            w.attributes("-alpha", 0.0)
        except Exception:
            pass
        if fullscreen:
            w.attributes("-fullscreen", True)
        else:
            w.overrideredirect(True)
            if geometry:
                w.geometry(geometry)
        windows.append(w)
        return w

    if monitors:
        for m in monitors:
            make_window(geometry=f"{m.width}x{m.height}+{m.x}+{m.y}")
        primary = windows[0]
    else:
        primary = make_window(fullscreen=True)

    def finish(value="completed"):
        if state["done"]:
            return
        state["done"] = True
        state["result"] = value
        try:
            root.quit()
        except Exception:
            pass

    _build_overlay_widgets(primary, message, duration, allow_skip, allow_snooze, finish)

    if not (allow_skip or allow_snooze):
        # Strict mode: swallow Escape so the break cannot be dismissed.
        primary.bind("<Escape>", lambda e: "break")
    else:
        primary.bind("<Escape>", lambda e: finish("skipped"))

    # Smooth fade-in across all screens.
    def fade(step=0):
        if state["done"]:
            return
        alpha = min(1.0, step / 12.0)
        for w in windows:
            try:
                w.attributes("-alpha", alpha)
            except Exception:
                pass
        if alpha < 1.0:
            root.after(25, fade, step + 1)

    end_time = time.time() + duration

    def tick():
        if state["done"]:
            return
        remaining = end_time - time.time()
        if remaining <= 0:
            finish("completed")
            return
        _update_overlay_countdown(primary, remaining, duration)
        root.after(200, tick)

    root.after(0, fade)
    root.after(50, lambda: _focus(primary))
    root.after(200, tick)

    try:
        root.mainloop()
    except Exception as e:
        print(f"[blinkly] Overlay error: {e}")
    finally:
        for w in windows:
            try:
                w.destroy()
            except Exception:
                pass
        try:
            root.destroy()
        except Exception:
            pass

    return state["result"]


def _focus(window):
    try:
        window.focus_force()
    except Exception:
        pass


def _build_overlay_widgets(window, message, duration, allow_skip, allow_snooze, finish):
    frame = tk.Frame(window, bg="black")
    frame.place(relx=0.5, rely=0.5, anchor="center")

    ring_size = 220
    canvas = tk.Canvas(frame, width=ring_size, height=ring_size, bg="black",
                       highlightthickness=0)
    canvas.pack(pady=(0, 24))
    pad = 14
    canvas.create_oval(pad, pad, ring_size - pad, ring_size - pad,
                       outline="#2b2b2b", width=10)
    window._ring_arc = canvas.create_arc(
        pad, pad, ring_size - pad, ring_size - pad,
        start=90, extent=-359.999, style="arc", outline="#3fd0c9", width=10)
    window._ring_text = canvas.create_text(
        ring_size / 2, ring_size / 2, text=str(int(duration)),
        fill="#ffffff", font=("Sans", 46, "bold"))
    window._ring_canvas = canvas
    window._ring_duration = duration

    tk.Label(frame, text=message, fg="#f2f2f2", bg="black",
             font=("Sans", 22), justify="center").pack(pady=(0, 8))
    tk.Label(frame, text="Blinkly", fg="#3fd0c9", bg="black",
             font=("Sans", 14, "bold")).pack(pady=(0, 20))

    if allow_skip or allow_snooze:
        btns = tk.Frame(frame, bg="black")
        btns.pack()
        if allow_snooze:
            tk.Button(btns, text="Snooze 5 min", command=lambda: finish("snoozed"),
                      bg="#2b2b2b", fg="white", activebackground="#3a3a3a",
                      activeforeground="white", relief="flat", bd=0,
                      padx=18, pady=8, font=("Sans", 12)).pack(side="left", padx=8)
        if allow_skip:
            tk.Button(btns, text="Skip (Esc)", command=lambda: finish("skipped"),
                      bg="#3fd0c9", fg="#08302e", activebackground="#57e0d9",
                      activeforeground="#08302e", relief="flat", bd=0,
                      padx=18, pady=8, font=("Sans", 12, "bold")).pack(side="left", padx=8)
    else:
        tk.Label(frame, text="Strict mode — enjoy your break",
                 fg="#8a8a8a", bg="black", font=("Sans", 12, "italic")).pack()


def _update_overlay_countdown(window, remaining, duration):
    canvas = getattr(window, "_ring_canvas", None)
    if canvas is None:
        return
    frac = max(0.0, min(1.0, remaining / duration))
    try:
        canvas.itemconfigure(window._ring_text, text=str(int(math.ceil(remaining))))
        canvas.itemconfigure(window._ring_arc, extent=-359.999 * frac)
    except Exception:
        pass


# ============================================================
# BREAK CONTROLLER (scheduling + orchestration)
# ============================================================

class BreakController:
    def __init__(self, manager: SettingsManager, break_stats: BreakStats):
        self.manager = manager
        self.stats = break_stats
        self.pause_until = 0.0
        self.next_break_at = time.time()
        self.next_micro_at = None
        self._scheduled_interval = None
        self._notified = False
        self.break_now = threading.Event()
        self.icon = None
        self._tray_icon_state = None

    # ---- pause helpers ----
    def paused_persistent(self) -> bool:
        return self.manager.current.pause_blinkly

    def is_paused(self) -> bool:
        return self.paused_persistent() or time.time() < self.pause_until

    def pause_for(self, minutes: int):
        self.pause_until = time.time() + minutes * 60
        print(f"[blinkly] Paused for {minutes} minutes.")

    def toggle_persistent_pause(self):
        s = self.manager.current
        updated = s.model_copy(update={"pause_blinkly": not s.pause_blinkly})
        self.manager.save(updated)

    def resume(self):
        self.pause_until = 0.0
        s = self.manager.current
        if s.pause_blinkly:
            self.manager.save(s.model_copy(update={"pause_blinkly": False}))
        self.schedule_next()

    def request_break_now(self):
        self.break_now.set()

    # ---- scheduling ----
    def schedule_next(self):
        s = self.manager.current
        self._scheduled_interval = s.break_interval
        self.next_break_at = time.time() + s.break_interval * 60
        self._notified = False

    def schedule_next_micro(self):
        s = self.manager.current
        self.next_micro_at = time.time() + s.micro_break_interval * 60

    # ---- main loop ----
    def run(self, icon=None):
        self.icon = icon
        self.schedule_next()
        self.schedule_next_micro()
        while True:
            try:
                self._loop_once()
            except Exception as e:
                print(f"[blinkly] Loop error: {e}")
            time.sleep(1)

    def _loop_once(self):
        s = self.manager.current
        now = time.time()
        self._update_tray()

        if self.is_paused():
            self.schedule_next()
            self.schedule_next_micro()
            return

        # Reschedule immediately if the interval was changed in settings.
        if self._scheduled_interval != s.break_interval:
            self.schedule_next()

        # Manual "take a break now".
        if self.break_now.is_set():
            self.break_now.clear()
            self._run_break(s, forced=True)
            self.schedule_next()
            return

        # Micro-break nudge (a gentle notification, not a fullscreen overlay).
        if s.micro_breaks_enabled and self.next_micro_at and now >= self.next_micro_at:
            self._do_micro_break(s)
            self.schedule_next_micro()

        # Pre-break notification.
        if (not self._notified and s.notify_before > 0
                and self.next_break_at - now <= s.notify_before):
            secs = max(1, int(round(self.next_break_at - now)))
            notify.send_notification(APP_NAME, f"Eye break in {secs}s — finish up.",
                                     icon=_notification_icon())
            self._notified = True

        # Break time.
        if now >= self.next_break_at:
            outcome = self._run_break(s)
            if outcome == "deferred":
                self.next_break_at = time.time() + FULLSCREEN_RETRY_SECONDS
                self._notified = True
            elif outcome == "snoozed":
                self.next_break_at = time.time() + SNOOZE_SECONDS
                self._notified = False
            else:
                self.schedule_next()

    def _run_break(self, s: SettingsModel, forced=False):
        # Already idle? Skip and reset (unless the user forced it).
        if not forced and s.idle_reset and idle_helper.is_idle(s.idle_threshold):
            print("[blinkly] User idle; skipping break and resetting timer.")
            return "idle"

        # Fullscreen app running? Defer (unless forced).
        if not forced and s.skip_on_fullscreen and fullscreen_helper.is_fullscreen_active():
            print("[blinkly] Fullscreen app active; deferring break.")
            return "deferred"

        sound_helper.play_sound(SOUND_FILE, volume=s.volume, enabled=s.sound_enabled)
        self._set_tray_break()

        allow = not s.strict_mode
        result = show_break_overlay(s.break_duration, LOOK_AWAY_MESSAGE,
                                    allow_skip=allow, allow_snooze=allow)
        if result == "snoozed":
            self.stats.record_skipped()
            return "snoozed"
        if result == "skipped":
            self.stats.record_skipped()
            return "skipped"
        self.stats.record_taken()
        return "completed"

    def _do_micro_break(self, s: SettingsModel):
        notify.send_notification(
            APP_NAME,
            f"Micro-break: blink and relax your eyes for {s.micro_break_duration}s.",
            urgency="low", icon=_notification_icon())

    # ---- tray rendering ----
    def _update_tray(self):
        if self.icon is None:
            return
        try:
            if self.is_paused():
                icon_state = ("paused",)
                if time.time() < self.pause_until:
                    mins = int((self.pause_until - time.time()) // 60) + 1
                    title = f"Blinkly paused ({mins} min left)"
                else:
                    title = "Blinkly paused"
            else:
                mins = max(0, math.ceil((self.next_break_at - time.time()) / 60))
                icon_state = ("active", mins)
                title = f"Next break in {mins} min"
            self.icon.title = title
            if icon_state != self._tray_icon_state:
                self._tray_icon_state = icon_state
                if icon_state[0] == "paused":
                    self.icon.icon = create_eye_icon(0, paused=True)
                else:
                    self.icon.icon = create_eye_icon(icon_state[1])
        except Exception as e:
            print(f"[blinkly] Tray update failed: {e}")

    def _set_tray_break(self):
        if self.icon is None:
            return
        try:
            self._tray_icon_state = ("break",)
            self.icon.icon = create_eye_icon(0)
            self.icon.title = "Break time!"
        except Exception:
            pass


def _notification_icon():
    for name in ("icon.png", "icon.svg"):
        p = ASSETS_DIR / name
        if p.exists():
            return p
    return None


# ============================================================
# TRAY MENU + STARTUP
# ============================================================

def build_tray_icon(controller: BreakController):
    def on_break_now(icon, item):
        controller.request_break_now()

    def on_toggle_pause(icon, item):
        controller.toggle_persistent_pause()

    def on_pause_30(icon, item):
        controller.pause_for(30)

    def on_pause_60(icon, item):
        controller.pause_for(60)

    def on_resume(icon, item):
        controller.resume()

    def on_open_settings(icon, item):
        open_settings_app_mode()

    def on_exit(icon, item):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Take a break now", on_break_now),
        pystray.MenuItem("Pause Blinkly", on_toggle_pause,
                         checked=lambda item: controller.paused_persistent()),
        pystray.MenuItem("Pause for 30 minutes", on_pause_30),
        pystray.MenuItem("Pause for 60 minutes", on_pause_60),
        pystray.MenuItem("Resume", on_resume),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Settings", on_open_settings),
        pystray.MenuItem("Exit", on_exit),
    )
    return pystray.Icon(
        "blinkly",
        icon=create_eye_icon(settings_manager.current.break_interval),
        title="Blinkly",
        menu=menu,
    )


def _print_pystray_help():
    print("[blinkly] System tray unavailable:", repr(_PYSTRAY_IMPORT_ERROR))
    if platform.system() == "Linux":
        print("[blinkly] On GNOME install the AppIndicator backend, then re-run:")
        print("[blinkly]   sudo apt install gir1.2-ayatanaappindicator3-0.1 python3-gi")
        print("[blinkly] and create the venv with --system-site-packages (see install.sh).")
    print("[blinkly] Continuing without a tray icon; open settings at", SETTINGS_URL)


def main():
    # Keep autostart in sync with the saved preference.
    try:
        autostart.sync_autostart(settings.autostart_enabled, app_name=APP_NAME)
        desktop_shortcut.create_shortcut(assets_dir=ASSETS_DIR)
    except Exception as e:
        print(f"[blinkly] Startup integration warning: {e}")

    threading.Thread(target=start_web_ui, daemon=True).start()
    if not settings.start_minimized:
        open_settings_page_when_ready()

    controller = BreakController(settings_manager, stats)

    if pystray is None:
        _print_pystray_help()
        # No tray: run the break loop directly so the app still works.
        controller.run(icon=None)
        return

    icon = build_tray_icon(controller)
    threading.Thread(target=controller.run, args=(icon,), daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
