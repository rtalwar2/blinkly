import os
import sys
import platform
from pathlib import Path
if platform.system() == "Windows":
    from win32com.client import Dispatch  # pip install pywin32


def create_shortcut( assets_dir,app_name="Blinkly", url="http://localhost:8000/"):
    system = platform.system()

    if system == "Windows":
        icon_path = assets_dir / "icon.ico"
        _create_shortcut_windows(app_name, url,icon_path)
    elif system == "Linux":
        icon_path = assets_dir / "icon.svg"
        _create_shortcut_linux(app_name, url, icon_path)
    elif system == "Darwin":
        _create_shortcut_macos(app_name, url, None)
    else:
        print(f"[shortcut] Unsupported platform: {system}")

# ------------------ WINDOWS ------------------
def _create_shortcut_windows(app_name, url, icon_path):
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    shortcut_path = os.path.join(desktop, f"{app_name}.lnk")

    if os.path.exists(shortcut_path):
        return

    # Browser detection order: Chrome -> Edge -> Firefox
    browsers = [
        (r"C:\Program Files\Google\Chrome\Application\chrome.exe", '--app="{url}" --window-size=900,700'),
        (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", '--app="{url}" --window-size=900,700'),
        (r"C:\Program Files\Mozilla Firefox\firefox.exe", '--kiosk "{url}"')
    ]

    for path, args_template in browsers:
        if os.path.exists(path):
            target = path
            arguments = args_template.format(url=url)
            break
    else:
        # fallback to default browser
        target = os.path.join(os.environ["WINDIR"], "System32", "cmd.exe")
        arguments = f'start {url}'

    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(shortcut_path)
    shortcut.Targetpath = target
    shortcut.Arguments = arguments
    shortcut.WorkingDirectory = os.path.dirname(sys.argv[0])
    if icon_path and icon_path.exists():
        shortcut.IconLocation = str(icon_path)
    shortcut.save()
    print(f"[shortcut] Created Windows desktop shortcut: {shortcut_path}")


# ------------------ LINUX ------------------
def _create_shortcut_linux(app_name, url, icon_path):
    desktop_file = Path.home() / "Desktop" / f"{app_name.lower().replace(' ', '_')}.desktop"
    if desktop_file.exists():
        return

    # Browser detection: Chrome, Chromium, Firefox
    browsers = [
        ("google-chrome", f'--app={url} --window-size=900,700'),
        ("chromium-browser", f'--app={url} --window-size=900,700'),
        ("firefox", f'--kiosk {url}')
    ]

    for browser_cmd, flags in browsers:
        if os.system(f"which {browser_cmd} > /dev/null 2>&1") == 0:
            exec_line = f"{browser_cmd} {flags}"
            break
    else:
        exec_line = f"xdg-open {url}"  # fallback

    icon_line = f"Icon={icon_path}" if icon_path and icon_path.exists() else ""
    content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name={app_name}
Comment=Open {app_name} settings
Exec={exec_line}
{icon_line}
Terminal=false
"""
    desktop_file.write_text(content)
    desktop_file.chmod(0o755)
    print(f"[shortcut] Created Linux desktop shortcut: {desktop_file}")


# ------------------ MACOS ------------------
def _create_shortcut_macos(app_name, url, icon_path):
    desktop_file = Path.home() / "Desktop" / f"{app_name}.command"
    if desktop_file.exists():
        return

    # Try Chrome or fallback to default
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    firefox_path = "/Applications/Firefox.app/Contents/MacOS/firefox"

    if Path(chrome_path).exists():
        exec_line = f'"{chrome_path}" --app="{url}" --window-size=900,700'
    elif Path(firefox_path).exists():
        exec_line = f'"{firefox_path}" --kiosk "{url}"'
    else:
        exec_line = f'open "{url}"'

    content = f"""#!/bin/bash
{exec_line}
"""
    desktop_file.write_text(content)
    desktop_file.chmod(0o755)
    print(f"[shortcut] Created macOS desktop shortcut: {desktop_file}")