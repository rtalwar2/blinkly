"""Best-effort detection of a fullscreen foreground window.

Lets Blinkly defer a break while you are watching a video, presenting, or
gaming.  Uses ``xprop`` (works under X11 and XWayland) to read the active
window's ``_NET_WM_STATE``.  On pure Wayland with no XWayland, or when ``xprop``
is missing, it safely returns ``False`` (do not skip the break).
"""

import shutil
import platform
import subprocess


def _run_xprop(args):
    return subprocess.run(["xprop", *args], capture_output=True, text=True, timeout=5)


def _active_window_id():
    out = _run_xprop(["-root", "_NET_ACTIVE_WINDOW"])
    if out.returncode != 0:
        return None
    # e.g. "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3e00007, 0x0"
    line = out.stdout.strip()
    if "#" not in line:
        return None
    win = line.split("#", 1)[1].strip().split(",")[0].strip()
    if not win or win == "0x0":
        return None
    return win


def is_fullscreen_active() -> bool:
    """Return True if the focused window advertises fullscreen state."""
    if platform.system() != "Linux" or not shutil.which("xprop"):
        return False
    try:
        win = _active_window_id()
        if not win:
            return False
        state = _run_xprop(["-id", win, "_NET_WM_STATE"])
        if state.returncode != 0:
            return False
        return "_NET_WM_STATE_FULLSCREEN" in state.stdout
    except Exception:
        return False


def available() -> bool:
    return platform.system() == "Linux" and shutil.which("xprop") is not None
