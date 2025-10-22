import time
import threading
import tkinter as tk
from screeninfo import get_monitors
import pystray
from PIL import Image, ImageDraw,ImageFont
from playsound import playsound
import json, os, webbrowser
import sys
from pathlib import Path
import traceback

# ===== FastAPI imports =====
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydantic import BaseModel, Field

import helpers.autostart as autostart
from appdirs import user_config_dir
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

class SettingsModel(BaseModel):
    break_interval: int = Field(20, description="Minutes between breaks", ge=1, le=180)
    break_duration: int = Field(20, description="Duration of break in seconds", ge=5, le=600)
    pause_blinkly:bool = Field(False,description="Pause Blinkly app")

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
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error",log_config=None)
        webbrowser.open("http://127.0.0.1:8000/")

    except Exception as e:
        # Log to a file for debugging (works in --windowed mode)
        with open("blinkly_error.log", "w", encoding="utf-8") as f:
            f.write("⚠️ FastAPI startup failed:\n")
            f.write(traceback.format_exc())

# ============================================================
# EYE BREAK CORE
# ============================================================

def create_eye_icon(minutes_left):
    width, height = 64, 64
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if settings_manager.current.pause_blinkly:
        draw.ellipse([8, 16, 56, 48], outline="white", width=4)
        draw.ellipse([26, 26, 38, 38], fill="white")
        draw.line([0, 0, width, height], fill="white", width=4)
    else:
        font_size = 64-8
        font=ImageFont.load_default(font_size)
        text=str(minutes_left)
        draw.text((-2,(64-font_size)/2-6),text,fill="white",font=font)
    return img


def show_black_screen(duration):
    """Show a full black overlay for `duration` seconds across all screens."""
    monitors = get_monitors()
    windows = []

    for monitor in monitors:
        root = tk.Tk()
        root.configure(bg="black")
        root.attributes("-topmost", True)
        root.attributes("-fullscreen", True)
        root.geometry(f"{monitor.width}x{monitor.height}+{monitor.x}+{monitor.y}")
        root.after(duration * 1000, root.destroy)
        windows.append(root)

    for root in windows:
        root.mainloop()


def run_overlay_loop(icon):
    while True:
        starttime = time.time()
        minutes_passed = (time.time()-starttime)//60
        while (minutes_passed<settings_manager.current.break_interval) and settings_manager.current.pause_blinkly==False:
            minutes_left = int(settings_manager.current.break_interval - minutes_passed)
            icon.icon = create_eye_icon(minutes_left)
            icon.title = f"Next break in {minutes_left} min"
            time.sleep(5)
            minutes_passed = (time.time()-starttime)//60
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

def on_open_settings(icon, item):
    webbrowser.open("http://127.0.0.1:8000/")

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
    autostart.ensure_autostart(app_name="Blinkly")
    start_tray_icon()
