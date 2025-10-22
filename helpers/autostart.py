import os
import sys
import platform
from pathlib import Path

# Optional: only needed on Windows for the message box + shortcut
if platform.system() == "Windows":
    import tkinter as tk
    from tkinter import messagebox
    from win32com.client import Dispatch  # pip install pywin32


def ensure_autostart(app_name="Eye Saver", ask_user=True, delay_seconds=10):
    """
    Ensures the app autostarts on login.
    Works on both Windows and Linux.

    :param app_name: Name of the app/shortcut/desktop file
    :param ask_user: Whether to ask before adding to autostart
    :param delay_seconds: Optional delay before starting (Linux only)
    """
    system = platform.system()

    if system == "Windows":
        _ensure_autostart_windows(app_name, ask_user)
    elif system == "Linux":
        _ensure_autostart_linux(app_name, delay_seconds)
    else:
        print(f"[autostart] Unsupported platform: {system}")


def _ensure_autostart_windows(app_name, ask_user):
    startup = os.path.join(
        os.getenv("APPDATA"), "Microsoft\\Windows\\Start Menu\\Programs\\Startup"
    )
    shortcut_path = os.path.join(startup, f"{app_name}.lnk")

    if os.path.exists(shortcut_path):
        return  # already installed

    if ask_user:
        root = tk.Tk()
        root.withdraw()
        result = messagebox.askyesno(
            f"{app_name} Autostart",
            f"Would you like {app_name} to start automatically when Windows starts?",
        )
        root.destroy()
        if not result:
            return

    target = sys.executable
    script = os.path.abspath(sys.argv[0])

    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(shortcut_path)
    shortcut.TargetPath = target
    shortcut.Arguments = f'"{script}"'
    shortcut.WorkingDirectory = os.path.dirname(script)
    shortcut.IconLocation = target
    shortcut.Save()

    print(f"[autostart] Created Windows Startup shortcut: {shortcut_path}")


def _ensure_autostart_linux(app_name, delay_seconds):
    autostart_dir = Path.home() / ".config" / "autostart"
    autostart_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = autostart_dir / f"{app_name.lower().replace(' ', '_')}.desktop"

    if desktop_file.exists():
        return  # already installed

    exec_path = f"sh -c 'sleep {delay_seconds} && {sys.executable}'"
    content = f"""[Desktop Entry]
Type=Application
Exec={exec_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name={app_name}
Comment=Starts {app_name} automatically on login
"""

    desktop_file.write_text(content)
    print(f"[autostart] Created Linux autostart entry: {desktop_file}")
