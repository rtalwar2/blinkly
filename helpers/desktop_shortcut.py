"""Create a desktop / application-menu launcher for Blinkly.

Linux notes:
* The launcher starts Blinkly itself (not a dead URL), reusing the same command
  builder as autostart, so clicking it in the app grid actually runs the app.
* We install into ``~/.local/share/applications`` (the app grid / menu) which is
  far more reliable on modern GNOME than dropping a file on the Desktop, and we
  *also* place a copy on the Desktop marked "trusted" so it is launchable there.
* ``shutil.which`` is used instead of ``os.system("which ...")``.
"""

import os
import sys
import shutil
import platform
import subprocess
from pathlib import Path

from . import autostart


def create_shortcut(assets_dir, app_name="Blinkly", url="http://localhost:8000/"):
    system = platform.system()
    assets_dir = Path(assets_dir)
    try:
        if system == "Linux":
            _create_shortcut_linux(app_name, assets_dir)
        elif system == "Windows":
            _create_shortcut_windows(app_name, url, assets_dir / "icon.ico")
        elif system == "Darwin":
            _create_shortcut_macos(app_name, url)
        else:
            print(f"[shortcut] Unsupported platform: {system}")
    except Exception as e:  # a missing launcher must never crash startup
        print(f"[shortcut] Could not create shortcut: {e}")


# ------------------ LINUX ------------------

def _linux_icon(assets_dir: Path):
    for name in ("icon.png", "icon.svg"):
        candidate = assets_dir / name
        if candidate.exists():
            return candidate
    return None


def _create_shortcut_linux(app_name, assets_dir):
    slug = app_name.lower().replace(" ", "_")
    icon = _linux_icon(assets_dir)
    icon_line = f"Icon={icon}\n" if icon else ""
    exec_line = autostart.build_autostart_command(0)

    content = (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        f"Name={app_name}\n"
        "Comment=Eye-break reminder to reduce eye strain\n"
        f"Exec={exec_line}\n"
        f"{icon_line}"
        "Terminal=false\n"
        "Categories=Utility;HealthAndFitness;\n"
        "Keywords=eye;break;health;reminder;20-20-20;\n"
        "StartupNotify=false\n"
    )

    # 1) App grid / application menu (reliable on GNOME).
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    apps_file = apps_dir / f"{slug}.desktop"
    apps_file.write_text(content)
    apps_file.chmod(0o755)
    _update_desktop_database(apps_dir)
    print(f"[shortcut] Installed application launcher: {apps_file}")

    # 2) Desktop copy, marked trusted so GNOME allows launching it.
    desktop_dir = _xdg_desktop_dir()
    if desktop_dir and desktop_dir.is_dir():
        desktop_file = desktop_dir / f"{slug}.desktop"
        if not desktop_file.exists():
            desktop_file.write_text(content)
            desktop_file.chmod(0o755)
            _mark_trusted(desktop_file)
            print(f"[shortcut] Created Desktop shortcut: {desktop_file}")


def _xdg_desktop_dir():
    """Resolve the user's Desktop directory (respects localized XDG config)."""
    try:
        out = subprocess.run(
            ["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5
        )
        path = Path(out.stdout.strip())
        if out.returncode == 0 and str(path) and path != Path.home():
            return path
    except Exception:
        pass
    fallback = Path.home() / "Desktop"
    return fallback if fallback.is_dir() else None


def _mark_trusted(desktop_file: Path):
    """Ask GNOME/Nautilus to trust the launcher so it runs on double-click."""
    if shutil.which("gio"):
        try:
            subprocess.run(
                ["gio", "set", str(desktop_file), "metadata::trusted", "true"],
                check=False, timeout=5,
            )
        except Exception:
            pass


def _update_desktop_database(apps_dir: Path):
    if shutil.which("update-desktop-database"):
        try:
            subprocess.run(
                ["update-desktop-database", str(apps_dir)], check=False, timeout=10
            )
        except Exception:
            pass


# ------------------ WINDOWS ------------------

def _create_shortcut_windows(app_name, url, icon_path):
    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    shortcut_path = os.path.join(desktop, f"{app_name}.lnk")
    if os.path.exists(shortcut_path):
        return

    from win32com.client import Dispatch  # pip install pywin32 (Windows only)

    target = sys.executable
    script = os.path.abspath(sys.argv[0])
    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(shortcut_path)
    shortcut.Targetpath = target
    if not getattr(sys, "frozen", False):
        shortcut.Arguments = f'"{script}"'
    shortcut.WorkingDirectory = os.path.dirname(script)
    if icon_path and Path(icon_path).exists():
        shortcut.IconLocation = str(icon_path)
    shortcut.save()
    print(f"[shortcut] Created Windows desktop shortcut: {shortcut_path}")


# ------------------ MACOS ------------------

def _create_shortcut_macos(app_name, url):
    desktop_file = Path.home() / "Desktop" / f"{app_name}.command"
    if desktop_file.exists():
        return
    launch = autostart.build_autostart_command(0)
    content = f"#!/bin/bash\n{launch}\n"
    desktop_file.write_text(content)
    desktop_file.chmod(0o755)
    print(f"[shortcut] Created macOS desktop shortcut: {desktop_file}")
