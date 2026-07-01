# Blinkly 👁️

A friendly eye-break reminder that helps you follow the **20-20-20 rule**
(every 20 minutes, look ~20 ft / 6 m away for 20 seconds) to reduce eye strain.

Blinkly lives in your system tray, gently dims every screen when it's time for a
break, and is configured from a small local settings page.

## Features

- Full-screen **break overlay** with a countdown ring and a "look away" prompt
- **Skip** (Esc) / **Snooze 5 min**, or **Strict mode** where breaks can't be skipped
- **Pre-break desktop notification** so breaks are never abrupt
- **Micro-break** blink reminders between full breaks
- **Sound cue** (optional) using whatever system player you have
- **Don't interrupt me**: automatically defers breaks during fullscreen apps and
  skips breaks when you're already away from the keyboard
- **Tray controls**: take a break now, pause for 30/60 minutes, resume
- **Daily stats**: breaks taken vs. skipped
- **Autostart on login** and presets (20-20-20, and more)

## Linux install (Ubuntu / Debian, GNOME included)

Blinkly needs a few system packages that can't come from `pip` (the tkinter
overlay and, on GNOME, the AppIndicator tray backend). The installer sets those
up and creates a virtual environment for the Python dependencies:

```bash
./install.sh          # installs system + Python deps (uses sudo for apt)
./run.sh              # start Blinkly
```

Prefer to do it by hand? The steps are:

```bash
sudo apt install python3-venv python3-tk python3-gi \
                 gir1.2-ayatanaappindicator3-0.1 libnotify-bin
# optional extras (features degrade gracefully without them):
sudo apt install ffmpeg xprintidle x11-utils

# IMPORTANT: --system-site-packages lets the venv see the system PyGObject /
# AppIndicator bindings that pystray needs for the GNOME tray icon.
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python blinkly.py
```

### What each system package is for

| Package | Enables |
|---|---|
| `python3-tk` | the break overlay (required) |
| `python3-gi` + `gir1.2-ayatanaappindicator3-0.1` | the system-tray icon on GNOME |
| `libnotify-bin` | pre-break desktop notifications |
| `ffmpeg` (ffplay) | the optional break sound |
| `xprintidle` | idle detection fallback (GNOME uses D-Bus first) |
| `x11-utils` (xprop) | detecting fullscreen apps to defer breaks |

## Usage

- Open **Settings** from the tray menu (or it opens automatically on first
  launch unless "Start minimized" is enabled). Settings live at
  <http://127.0.0.1:8000/>.
- The tray icon shows the minutes until your next break. Right-click it for
  *Take a break now*, *Pause for 30/60 minutes*, *Resume*, *Open Settings* and
  *Exit*.
- Settings are stored in your user config dir
  (`~/.config/Blinkly/blinkly_settings.json`).

## Notes for GNOME / Wayland

- The tray icon uses **AppIndicator**. Ubuntu ships the required GNOME extension
  (`ubuntu-appindicators`) enabled by default; you only need the
  `gir1.2-ayatanaappindicator3-0.1` typelib (installed above).
- The break overlay and fullscreen detection run through **XWayland**, which is
  present on a standard Ubuntu GNOME session, so multi-monitor overlays work.

## Troubleshooting

- **No tray icon** → install `gir1.2-ayatanaappindicator3-0.1` and make sure the
  venv was created with `--system-site-packages`. Blinkly prints a hint and
  keeps running (open the settings URL directly).
- **No break overlay** → install `python3-tk`.
- **`pip install` failed with pywin32** → make sure you're on the current
  `requirements.txt`; `pywin32` is now Windows-only.
- **No sound** → install `ffmpeg`, or turn sound off in Settings.

## Other platforms

Blinkly also runs on Windows and macOS. On Windows, `pip install -r
requirements.txt` pulls in `pywin32` automatically; tray, sound (`winsound`) and
notifications work out of the box.

## Building a standalone binary

See [`install_blinkly.txt`](install_blinkly.txt) for the PyInstaller commands.
