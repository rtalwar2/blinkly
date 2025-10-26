import time
import socket
import webview

def wait_for_backend(host="127.0.0.1", port=8000, timeout=10):
    """Wait until backend is reachable."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False

if __name__ == "__main__":
    if wait_for_backend():
        webview.create_window(
            "Blinkly Settings",
            "http://127.0.0.1:8000/",
            width=650,
            height=550,
            resizable=True,
            confirm_close=False,
        )
        webview.start(debug=False)
    else:
        print("⚠️ Could not connect to backend (is Blinkly running?)")
