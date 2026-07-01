#!/usr/bin/env bash
#
# Blinkly installer for Debian/Ubuntu-based Linux (tested on Ubuntu 24.04, GNOME/Wayland).
#
# It installs the system packages that cannot come from pip, creates a virtual
# environment that can see the system PyGObject/AppIndicator bindings (required
# for the tray icon on GNOME), and installs the Python dependencies.
#
# Usage:
#   ./install.sh            # install everything
#   ./install.sh --no-apt   # skip the apt step (deps already installed)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
RUN_APT=1

for arg in "$@"; do
  case "$arg" in
    --no-apt) RUN_APT=0 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

# --- 1. System packages ------------------------------------------------------
# python3-tk .......................... tkinter (the break overlay) - NOT pip-installable
# python3-gi + gir1.2-ayatana... ...... AppIndicator tray backend for pystray on GNOME
# python3-venv ........................ virtual environments
# libnotify-bin ....................... notify-send (pre-break desktop notifications)
# Optional (features degrade gracefully without them):
#   ffmpeg ............................ ffplay, the most reliable Linux sound player for mp3
#   xprintidle ........................ idle detection fallback (GNOME uses dbus first)
#   x11-utils ......................... xprop, used to skip breaks during fullscreen apps
APT_PACKAGES=(
  python3-venv
  python3-tk
  python3-gi
  gir1.2-ayatanaappindicator3-0.1
  libnotify-bin
  ffmpeg
  xprintidle
  x11-utils
)

if [ "$RUN_APT" -eq 1 ]; then
  if command -v apt-get >/dev/null 2>&1; then
    echo ">> Installing system packages (sudo required):"
    printf '   - %s\n' "${APT_PACKAGES[@]}"
    sudo apt-get update
    sudo apt-get install -y "${APT_PACKAGES[@]}"
  else
    echo "!! apt-get not found. This script targets Debian/Ubuntu."
    echo "   Install the equivalent of: ${APT_PACKAGES[*]}"
    echo "   then re-run with: ./install.sh --no-apt"
    exit 1
  fi
else
  echo ">> Skipping apt step (--no-apt)."
fi

# --- 2. Virtual environment --------------------------------------------------
# --system-site-packages is REQUIRED so the venv can import the system `gi`
# (PyGObject) + AppIndicator typelib that pystray needs for the GNOME tray.
if [ ! -d "$VENV_DIR" ]; then
  echo ">> Creating virtual environment in $VENV_DIR (with --system-site-packages)"
  python3 -m venv --system-site-packages "$VENV_DIR"
else
  echo ">> Reusing existing virtual environment in $VENV_DIR"
fi

# --- 3. Python dependencies --------------------------------------------------
echo ">> Installing Python dependencies"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt

echo
echo "Done. Run Blinkly with:"
echo "    ./run.sh"
echo "  or"
echo "    $VENV_DIR/bin/python blinkly.py"
