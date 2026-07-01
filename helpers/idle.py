"""Detect how long the user has been idle (no input).

Used so Blinkly does not fire a break while you are already away from the
keyboard, and resets the timer instead.  On GNOME the Mutter ``IdleMonitor`` is
queried over D-Bus via ``gdbus`` (no extra Python dependency); ``xprintidle`` is
used as a fallback.  If neither is available, ``get_idle_seconds`` returns
``None`` which callers treat as "unknown / assume active".
"""

import re
import shutil
import platform
import subprocess


def _query_mutter_idle_ms():
    if not shutil.which("gdbus"):
        return None
    try:
        out = subprocess.run(
            [
                "gdbus", "call", "--session",
                "--dest", "org.gnome.Mutter.IdleMonitor",
                "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
                "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return None
        # Output looks like: "(uint64 12345,)" -- capture only the argument,
        # NOT the "64" from the "uint64" type tag.
        m = re.search(r"uint64\s+(\d+)", out.stdout)
        if m:
            return int(m.group(1))
        # Fall back to any bare integer if the type tag is absent.
        m = re.search(r"(\d+)", out.stdout)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _query_xprintidle_ms():
    if not shutil.which("xprintidle"):
        return None
    try:
        out = subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=5)
        if out.returncode != 0:
            return None
        return int(out.stdout.strip())
    except Exception:
        return None


def get_idle_seconds():
    """Return idle time in seconds, or ``None`` if it cannot be determined."""
    if platform.system() != "Linux":
        return None
    ms = _query_mutter_idle_ms()
    if ms is None:
        ms = _query_xprintidle_ms()
    return None if ms is None else ms / 1000.0


def is_idle(threshold_seconds) -> bool:
    """True only if idle time is known and exceeds ``threshold_seconds``."""
    idle = get_idle_seconds()
    return idle is not None and idle >= threshold_seconds


def available() -> bool:
    return get_idle_seconds() is not None
