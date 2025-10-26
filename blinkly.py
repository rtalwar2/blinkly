import time
import threading
import tkinter as tk
from screeninfo import get_monitors
import pystray
from PIL import Image, ImageDraw, ImageFont
from playsound import playsound
import json, os, webbrowser
import sys
from pathlib import Path
import traceback
import platform

# ===== FastAPI imports =====
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydantic import BaseModel, Field

from helpers import desktop_shortcut
import helpers.autostart as autostart
from appdirs import user_config_dir
import shutil
import subprocess
# ============================================================
# CONFIGURATION & MODEL
# ============================================================


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller."""
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(__file__).parent
    return base_path / relative_path


APP_NAME = "Blinkly"
CONFIG_DIR = Path(user_config_dir(APP_NAME))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = CONFIG_DIR / "blinkly_settings.json"

STATIC_DIR = resource_path("static")
sound_file = resource_path("./assets/pan2.mp3")
ASSETS_DIR = resource_path("assets")


class SettingsModel(BaseModel):
    break_interval: int = Field(20, description="Minutes between breaks", ge=1, le=180)
    break_duration: int = Field(
        20, description="Duration of break in seconds", ge=5, le=600
    )
    pause_blinkly: bool = Field(False, description="Pause Blinkly app")


class SettingsManager:
    def __init__(self, path: Path, default: SettingsModel):
        self.path = path
        self._data = default

    def load(self) -> SettingsModel:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._data = SettingsModel(**data)
            except Exception as e:
                print(f"[WARN] Failed to load settings: {e}")
        return self._data

    def save(self, model: SettingsModel):
        self.path.write_text(model.model_dump_json(indent=2))
        self._data = model

    @property
    def current(self) -> SettingsModel:
        return self._data


settings_manager = SettingsManager(SETTINGS_FILE, SettingsModel())
settings = settings_manager.load()

# ============================================================
# FASTAPI SETTINGS PANEL
# ============================================================

app = FastAPI()


@app.get("/api/settings")
def get_settings():
    """Return current settings as JSON."""
    return settings_manager.current.model_dump()


@app.post("/api/save", response_class=JSONResponse)
def save_settings_api(
    interval: int = Form(...),
    duration: int = Form(...),
    pause_blinkly: bool = Form(False),
):
    """Handle settings update."""
    model = SettingsModel(
        break_interval=interval,
        break_duration=duration,
        pause_blinkly=pause_blinkly,
    )
    settings_manager.save(model)
    return {"status": "ok", "message": "Settings saved successfully"}


# serve static files (your HTML frontend)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="settings")


def start_web_ui():
    """Run FastAPI server in a background thread (with silent error handling)."""
    try:
        uvicorn.run(
            app, host="127.0.0.1", port=8000, log_level="error", log_config=None
        )
        webbrowser.open("http://127.0.0.1:8000/")

    except Exception as e:
        # Log to a file for debugging (works in --windowed mode)
        with open("blinkly_error.log", "w", encoding="utf-8") as f:
            f.write("⚠️ FastAPI startup failed:\n")
            f.write(traceback.format_exc())


import socket


def open_settings_page_when_ready(url="http://127.0.0.1:8000/", timeout=20):
    """Wait until FastAPI server is reachable, then open the settings page."""

    def _wait_and_open():
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Try connecting to port 8000
                with socket.create_connection(("127.0.0.1", 8000), timeout=1):
                    open_settings_app_mode()
                    return
            except (OSError, ConnectionRefusedError):
                time.sleep(0.5)
        # If it never came up, still try to open (browser will show error)
        open_settings_app_mode()

    threading.Thread(target=_wait_and_open, daemon=True).start()


# ============================================================
# EYE BREAK CORE
# ============================================================


def create_eye_icon(minutes_left):
    width, height = 64, 64
    img = Image.new("RGB", (width, height), "black")

    if platform.system() == "Windows":
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    draw = ImageDraw.Draw(img)
    if settings_manager.current.pause_blinkly:
        draw.ellipse([8, 16, 56, 48], outline="white", width=4)
        draw.ellipse([26, 26, 38, 38], fill="white")
        draw.line([0, 0, width, height], fill="white", width=4)
    else:
        font_size = 64 - 8
        if minutes_left / 100 > 1:
            font_size = 38
        font = ImageFont.load_default(font_size)
        text = str(minutes_left)
        if len(text) == 3:
            draw.text((-2, (64 - font_size) / 2 - 6), text, fill="white", font=font)
        elif len(text) == 2:
            draw.text((-2, (64 - font_size) / 2 - 6), text, fill="white", font=font)
        elif len(text) == 1:
            draw.text((16, (64 - font_size) / 2 - 6), text, fill="white", font=font)
    return img


def show_black_screen(duration):
    """Show a full black overlay for `duration` seconds across all screens."""
    monitors = get_monitors()
    windows = []

    def fade_in(window):
        steps = 50
        fade_time = 1
        for i in range(steps + 1):
            alpha = i / steps
            if platform.system() == "Windows":
                window.attributes("-alpha", alpha)
            elif platform.system() == "Linux":
                window.wm_attributes("-alpha", alpha)
            window.update()
            time.sleep(fade_time / steps)

    for monitor in monitors:
        root = tk.Tk()
        root.configure(bg="black")
        root.attributes("-topmost", True)
        if platform.system() == "Windows":
            root.attributes("-alpha", 0.0)
        elif platform.system() == "Linux":
            root.wm_attributes("-alpha", 0.8)
        root.attributes("-fullscreen", True)
        root.geometry(f"{monitor.width}x{monitor.height}+{monitor.x}+{monitor.y}")
        root.after(duration * 1000, root.destroy)
        root.after(10, fade_in, root)
        windows.append(root)

    for root in windows:
        root.mainloop()


def run_overlay_loop(icon):
    while True:
        starttime = time.time()
        minutes_passed = (time.time() - starttime) // 60
        while (
            minutes_passed < settings_manager.current.break_interval
        ) and settings_manager.current.pause_blinkly == False:
            minutes_left = int(settings_manager.current.break_interval - minutes_passed)
            icon.icon = create_eye_icon(minutes_left)
            icon.title = f"Next break in {minutes_left} min"
            time.sleep(5)
            minutes_passed = (time.time() - starttime) // 60
        if not settings_manager.current.pause_blinkly:
            duration = settings_manager.current.break_duration
            icon.icon = create_eye_icon(0)
            icon.title = "Break time!"
            show_black_screen(duration)
            # playsound(str(sound_file))
        else:
            icon.icon = create_eye_icon(0)
            icon.title = f"Blinkly paused"
            time.sleep(5)


def on_exit(icon, item):
    icon.stop()


def open_settings_app_mode():
    url = "http://127.0.0.1:8000/"
    system = platform.system()

    if system == "Windows":
        # Try Chrome first
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        firefox_path = r"C:\Program Files\Mozilla Firefox\firefox.exe"

        if shutil.which(chrome_path):
            subprocess.Popen([chrome_path, f"--app={url}", "--window-size=900,700"])
        elif shutil.which(edge_path):
            subprocess.Popen([edge_path, f"--app={url}", "--window-size=900,700"])
        elif shutil.which(firefox_path):
            subprocess.Popen([firefox_path, f"--kiosk", url])
        else:
            subprocess.Popen(["start", url], shell=True)

    elif system == "Linux":
        if shutil.which("google-chrome"):
            subprocess.Popen(["google-chrome", f"--app={url}", "--window-size=900,700"])
        elif shutil.which("chromium-browser"):
            subprocess.Popen(["chromium-browser", f"--app={url}", "--window-size=900,700"])
        elif shutil.which("firefox"):
            subprocess.Popen(["firefox", "--kiosk", url])
        else:
            subprocess.Popen(["xdg-open", url])

    elif system == "Darwin":
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        firefox_path = "/Applications/Firefox.app/Contents/MacOS/firefox"
        if Path(chrome_path).exists():
            subprocess.Popen([chrome_path, f"--app={url}", "--window-size=900,700"])
        elif Path(firefox_path).exists():
            subprocess.Popen([firefox_path, "--kiosk", url])
        else:
            subprocess.Popen(["open", url])


def on_open_settings(icon, item):
    # webbrowser.open("http://127.0.0.1:8000/")
    open_settings_app_mode()

def start_tray_icon():
    initial_icon = create_eye_icon(settings.break_interval)
    icon = pystray.Icon(
        "eye_break",
        icon=initial_icon,
        title="Eye Break Reminder",
        menu=pystray.Menu(
            pystray.MenuItem("Open Settings", on_open_settings),
            pystray.MenuItem("Exit", on_exit),
        ),
    )

    threading.Thread(target=run_overlay_loop, args=(icon,), daemon=True).start()
    threading.Thread(target=start_web_ui, daemon=True).start()

    icon.run()


if __name__ == "__main__":
    if autostart.ensure_autostart(app_name="Blinkly"):
        desktop_shortcut.create_shortcut(assets_dir=ASSETS_DIR)
    open_settings_page_when_ready()
    start_tray_icon()
