"""Desktop notifications (used for pre-break warnings and micro-breaks).

Best-effort and cross-platform: uses ``notify-send`` on Linux, ``osascript`` on
macOS, and pystray's balloon on Windows (passed in by the caller).  Every path
is wrapped so a missing tool simply returns ``False`` instead of raising.
"""

import shutil
import platform
import subprocess
from pathlib import Path

_DEVNULL = subprocess.DEVNULL


def available() -> bool:
    system = platform.system()
    if system == "Linux":
        return shutil.which("notify-send") is not None
    if system == "Darwin":
        return shutil.which("osascript") is not None
    return system == "Windows"


def send_notification(title, message, urgency="normal", icon=None, app_name="Blinkly") -> bool:
    """Show a desktop notification. Returns True if it was dispatched."""
    system = platform.system()
    try:
        if system == "Linux":
            return _notify_linux(title, message, urgency, icon, app_name)
        if system == "Darwin":
            return _notify_macos(title, message)
        # Windows notifications are handled by the tray icon (icon.notify);
        # there is no reliable standalone CLI, so treat as unsupported here.
        return False
    except Exception as e:
        print(f"[notify] Failed to send notification: {e}")
        return False


def _notify_linux(title, message, urgency, icon, app_name) -> bool:
    if not shutil.which("notify-send"):
        return False
    args = ["notify-send", "-a", app_name, "-u", _clamp_urgency(urgency), "-t", "8000"]
    if icon and Path(str(icon)).exists():
        args += ["-i", str(icon)]
    args += [str(title), str(message)]
    subprocess.Popen(args, stdout=_DEVNULL, stderr=_DEVNULL)
    return True


def _notify_macos(title, message) -> bool:
    if not shutil.which("osascript"):
        return False
    script = f'display notification {_osa_quote(message)} with title {_osa_quote(title)}'
    subprocess.Popen(["osascript", "-e", script], stdout=_DEVNULL, stderr=_DEVNULL)
    return True


def _clamp_urgency(urgency):
    return urgency if urgency in ("low", "normal", "critical") else "normal"


def _osa_quote(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'
