"""Play the break sound through whatever system player is available.

The old ``playsound`` dependency was unreliable on Linux (and disabled in the
code).  Instead we shell out to the first working player, preferring ones that
handle the bundled mp3.  Volume is applied where the player supports it.  If no
player is found the call is a clean no-op that returns ``False``.
"""

import shutil
import platform
import subprocess
from pathlib import Path

_DEVNULL = subprocess.DEVNULL


def _clamp_volume(volume):
    try:
        return max(0, min(100, int(volume)))
    except (TypeError, ValueError):
        return 80


def _linux_player_command(path, volume):
    """Return argv for the first available Linux player, or None."""
    path = str(path)
    vol = _clamp_volume(volume)

    # ffplay / mpg123 handle mp3 reliably; paplay/aplay are for wav/ogg;
    # canberra is the desktop-native fallback.
    if shutil.which("ffplay"):
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                "-volume", str(vol), path]
    if shutil.which("mpg123"):
        scale = int(vol / 100 * 32768)
        return ["mpg123", "-q", "-f", str(scale), path]
    if shutil.which("paplay"):
        pa_vol = int(vol / 100 * 65536)
        return ["paplay", f"--volume={pa_vol}", path]
    if shutil.which("canberra-gtk-play"):
        return ["canberra-gtk-play", "-f", path]
    if shutil.which("aplay") and path.lower().endswith(".wav"):
        return ["aplay", "-q", path]
    return None


def available() -> bool:
    system = platform.system()
    if system == "Linux":
        return _linux_player_command("x", 80) is not None
    if system == "Darwin":
        return shutil.which("afplay") is not None
    return system == "Windows"


def play_sound(path, volume=80, enabled=True) -> bool:
    """Play ``path`` asynchronously. Returns True if a player was launched."""
    if not enabled:
        return False
    path = Path(path)
    if not path.exists():
        print(f"[sound] Sound file not found: {path}")
        return False

    system = platform.system()
    try:
        if system == "Linux":
            cmd = _linux_player_command(path, volume)
        elif system == "Darwin":
            cmd = ["afplay", str(path)] if shutil.which("afplay") else None
        elif system == "Windows":
            return _play_windows(path)
        else:
            cmd = None

        if not cmd:
            print("[sound] No supported audio player found; skipping sound.")
            return False
        subprocess.Popen(cmd, stdout=_DEVNULL, stderr=_DEVNULL)
        return True
    except Exception as e:
        print(f"[sound] Failed to play sound: {e}")
        return False


def _play_windows(path) -> bool:
    try:
        import winsound  # stdlib, Windows only
        # winsound.PlaySound with SND_FILENAME only supports WAV/PCM files.
        # The bundled cue is an MP3, which it cannot play, so fall back to a
        # guaranteed-audible system sound for anything that isn't a WAV.
        if str(path).lower().endswith(".wav"):
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            winsound.MessageBeep(winsound.MB_OK)
        return True
    except Exception as e:
        print(f"[sound] winsound failed: {e}")
        return False
