"""
Folder Browser - mini HTTP server chay tren agent
Cho phep web UI duyet thu muc cua may client (Win 2012)

Endpoint:
- GET /folders/list?path=C:\\  -> liet ke thu muc con va file tai path
- GET /folders/quick           -> danh sach quick picks (Desktop, Documents...)

Chay nhu thread nen trong agent.py, lang nghe port 5001
"""
# Auto-add shared/ to import path (cho phep import config, database, snapshot, encryption_utils)
import sys
import os
_SHARED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import os
import platform
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

IS_WINDOWS = platform.system() == "Windows"
BROWSER_PORT = 5001


def get_drives():
    """Lay danh sach drive co san (C:, D:, ...)"""
    if not IS_WINDOWS:
        return ["/", "/home", "/tmp"]
    drives = []
    import string
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            drives.append(drive)
    return drives


def get_quick_picks():
    """Danh sach folder thuong dung"""
    picks = []
    if not IS_WINDOWS:
        for p in ["/home", "/tmp", "/var/log"]:
            if os.path.exists(p):
                picks.append({"name": p, "path": p, "icon": "folder"})
        return picks

    userprofile = os.environ.get("USERPROFILE", "C:\\Users\\Administrator")
    candidates = [
        ("Desktop", os.path.join(userprofile, "Desktop"), "desktop"),
        ("Documents", os.path.join(userprofile, "Documents"), "file-earmark-text"),
        ("Downloads", os.path.join(userprofile, "Downloads"), "download"),
        ("Pictures", os.path.join(userprofile, "Pictures"), "image"),
        ("User Profile", userprofile, "person"),
        ("C:\\ Drive", "C:\\", "hdd"),
        ("Program Files", "C:\\Program Files", "boxes"),
        ("Program Files (x86)", "C:\\Program Files (x86)", "boxes"),
    ]
    for name, path, icon in candidates:
        if os.path.exists(path):
            picks.append({"name": name, "path": path, "icon": icon})

    # Them cac drive khac (D:, E:...)
    for drive in get_drives():
        if drive != "C:\\":
            picks.append({"name": f"{drive} Drive", "path": drive, "icon": "hdd"})
    return picks


def list_directory(path):
    """
    Liet ke thu muc con tai path.
    Tra ve: { current, parent, folders: [{name, path, size}], files: [...] }
    """
    if not path:
        # Tra ve root - liet ke cac drive
        if IS_WINDOWS:
            return {
                "current": "",
                "parent": None,
                "folders": [{"name": d, "path": d, "is_drive": True}
                            for d in get_drives()],
                "files": []
            }
        else:
            path = "/"

    # Chuan hoa path
    path = os.path.normpath(path)

    if not os.path.exists(path):
        return {"error": f"Path khong ton tai: {path}"}
    if not os.path.isdir(path):
        return {"error": f"Khong phai thu muc: {path}"}

    folders = []
    files = []
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_dir(follow_symlinks=False):
                    folders.append({
                        "name": entry.name,
                        "path": entry.path,
                        "is_drive": False
                    })
                elif entry.is_file(follow_symlinks=False):
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                    files.append({
                        "name": entry.name,
                        "path": entry.path,
                        "size": size
                    })
            except (PermissionError, OSError):
                continue
    except PermissionError:
        return {"error": "Khong co quyen truy cap thu muc nay"}
    except OSError as e:
        return {"error": str(e)}

    # Sap xep alphabetical
    folders.sort(key=lambda x: x["name"].lower())
    files.sort(key=lambda x: x["name"].lower())

    # Parent path
    parent = os.path.dirname(path.rstrip(os.sep))
    if IS_WINDOWS and len(path) <= 3:  # Drive root nhu C:\
        parent = ""  # Quay ve list drives

    return {
        "current": path,
        "parent": parent if parent != path else None,
        "folders": folders,
        "files": files[:200]  # Gioi han 200 file mot luc
    }


class BrowserHandler(BaseHTTPRequestHandler):
    """HTTP handler cho folder browser"""

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/folders/list":
            path = params.get("path", [""])[0]
            try:
                self._send_json(list_directory(path))
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif parsed.path == "/folders/quick":
            try:
                self._send_json({
                    "quick_picks": get_quick_picks(),
                    "drives": get_drives(),
                    "hostname": platform.node()
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif parsed.path == "/folders/ping":
            self._send_json({"ok": True, "hostname": platform.node()})

        else:
            self._send_json({"error": "Not found"}, 404)

    def log_message(self, fmt, *args):
        # Tat log mac dinh de khong spam console agent
        pass


def start_browser_server():
    """Khoi dong mini-server trong thread nen"""
    def _run():
        try:
            httpd = HTTPServer(("0.0.0.0", BROWSER_PORT), BrowserHandler)
            print(f"[folder_browser] Lang nghe tai port {BROWSER_PORT}")
            httpd.serve_forever()
        except Exception as e:
            print(f"[folder_browser] Loi: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    start_browser_server()
    import time
    print("Folder browser dang chay. Nhan Ctrl+C de dung.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
