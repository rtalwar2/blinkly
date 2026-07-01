"""Cross-platform autostart (run Blinkly on login) management.

The previous implementation popped up a tkinter dialog on every first run and,
on Linux, generated an ``Exec`` line that launched a bare Python interpreter
instead of the app.  Autostart is now driven by the app settings
(``autostart_enabled``) and exposes small, testable helpers:

    set_autostart(True/False)      -> create / remove the autostart entry
    is_autostart_enabled()         -> bool
    sync_autostart(enabled)        -> make the on-disk state match ``enabled``
    build_autostart_command(...)   -> the command used to relaunch Blinkly
                                       (also unit-testable in isolation)

No GUI toolkit is imported here, so a missing ``python3-tk`` no longer prevents
autostart from working.
"""

import os
import sys
import shlex
import platform
from pathlib import Path


def _autostart_slug(app_name: str) -> str:
    return app_name.lower().replace(" ", "_")


def build_autostart_command(delay_seconds: int = 0) -> str:
    """Return the shell command that (re)launches Blinkly.

    Works both when running from source (python + script path) and when frozen
    by PyInstaller (``sys.executable`` is the app binary itself).  An optional
    ``delay_seconds`` wraps the command in ``sh -c 'sleep N && exec ...'`` so the
    desktop is ready before Blinkly starts.
    """
    if getattr(sys, "frozen", False):
        # Frozen build: sys.executable IS the application.
        cmd = shlex.quote(sys.executable)
    else:
        python = shlex.quote(sys.executable)
        script = shlex.quote(os.path.abspath(sys.argv[0]))
        cmd = f"{python} {script}"

    if delay_seconds and delay_seconds > 0:
        inner = f"sleep {int(delay_seconds)} && exec {cmd}"
        return f"sh -c {shlex.quote(inner)}"
    return cmd


# ============================================================
# Public API
# ============================================================

def set_autostart(enabled: bool, app_name: str = "Blinkly", delay_seconds: int = 10) -> bool:
    """Create or remove the autostart entry. Returns the resulting enabled state."""
    system = platform.system()
    try:
        if system == "Linux":
            return _set_autostart_linux(enabled, app_name, delay_seconds)
        if system == "Windows":
            return _set_autostart_windows(enabled, app_name)
        if system == "Darwin":
            return _set_autostart_macos(enabled, app_name)
    except Exception as e:  # never let autostart management crash the app
        print(f"[autostart] Failed to update autostart: {e}")
        return is_autostart_enabled(app_name)
    print(f"[autostart] Unsupported platform: {system}")
    return False


def is_autostart_enabled(app_name: str = "Blinkly") -> bool:
    system = platform.system()
    if system == "Linux":
        return _linux_desktop_file(app_name).exists()
    if system == "Windows":
        return _windows_shortcut_path(app_name).exists()
    if system == "Darwin":
        return _macos_plist_path(app_name).exists()
    return False


def sync_autostart(enabled: bool, app_name: str = "Blinkly", delay_seconds: int = 10) -> bool:
    """Make the on-disk autostart state match ``enabled`` (idempotent)."""
    if is_autostart_enabled(app_name) == bool(enabled):
        return bool(enabled)
    return set_autostart(enabled, app_name, delay_seconds)


# ------------------------------------------------------------
# Linux
# ------------------------------------------------------------

def _linux_desktop_file(app_name: str) -> Path:
    return Path.home() / ".config" / "autostart" / f"{_autostart_slug(app_name)}.desktop"


def _set_autostart_linux(enabled: bool, app_name: str, delay_seconds: int) -> bool:
    desktop_file = _linux_desktop_file(app_name)
    if not enabled:
        if desktop_file.exists():
            desktop_file.unlink()
            print(f"[autostart] Removed Linux autostart entry: {desktop_file}")
        return False

    desktop_file.parent.mkdir(parents=True, exist_ok=True)
    exec_line = build_autostart_command(delay_seconds)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Exec={exec_line}\n"
        "Hidden=false\n"
        "NoDisplay=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        f"Name={app_name}\n"
        f"Comment=Starts {app_name} automatically on login\n"
    )
    desktop_file.write_text(content)
    print(f"[autostart] Created Linux autostart entry: {desktop_file}")
    return True


# ------------------------------------------------------------
# Windows
# ------------------------------------------------------------

def _windows_shortcut_path(app_name: str) -> Path:
    startup = os.path.join(
        os.getenv("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    return Path(startup) / f"{app_name}.lnk"


def _set_autostart_windows(enabled: bool, app_name: str) -> bool:
    shortcut_path = _windows_shortcut_path(app_name)
    if not enabled:
        if shortcut_path.exists():
            shortcut_path.unlink()
            print(f"[autostart] Removed Windows Startup shortcut: {shortcut_path}")
        return False

    from win32com.client import Dispatch  # pip install pywin32 (Windows only)

    target = sys.executable
    script = os.path.abspath(sys.argv[0])
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)

    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(shortcut_path))
    shortcut.TargetPath = target
    if not getattr(sys, "frozen", False):
        shortcut.Arguments = f'"{script}"'
    shortcut.WorkingDirectory = os.path.dirname(script)
    shortcut.IconLocation = target
    shortcut.Save()
    print(f"[autostart] Created Windows Startup shortcut: {shortcut_path}")
    return True


# ------------------------------------------------------------
# macOS
# ------------------------------------------------------------

def _macos_plist_path(app_name: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"com.{_autostart_slug(app_name)}.plist"


def _set_autostart_macos(enabled: bool, app_name: str) -> bool:
    plist_path = _macos_plist_path(app_name)
    if not enabled:
        if plist_path.exists():
            plist_path.unlink()
            print(f"[autostart] Removed macOS LaunchAgent: {plist_path}")
        return False

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    program_args = [sys.executable]
    if not getattr(sys, "frozen", False):
        program_args.append(os.path.abspath(sys.argv[0]))
    args_xml = "".join(f"        <string>{a}</string>\n" for a in program_args)
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>com.{_autostart_slug(app_name)}</string>\n"
        "    <key>ProgramArguments</key>\n"
        f"    <array>\n{args_xml}    </array>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "</dict>\n"
        "</plist>\n"
    )
    plist_path.write_text(content)
    print(f"[autostart] Created macOS LaunchAgent: {plist_path}")
    return True
