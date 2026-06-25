"""
Remote Storage Client - chay tren agent (Win 2012)
Giao tiep voi storage server (Win 2016) qua HTTP de upload/download file backup

Moi user co folder rieng tren server, dinh danh boi token
"""
# Auto-add shared/ to import path (cho phep import config, database, snapshot, encryption_utils)
import sys
import os
_SHARED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import os
import requests
import config


class RemoteStorageClient:
    """Client de upload/download file len storage server"""

    def __init__(self, server_url, token):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        # Doan timeout dai cho file lon
        self.upload_timeout = 600  # 10 phut
        self.download_timeout = 600

    def _headers(self):
        return {"X-Auth-Token": self.token}

    def upload(self, local_path, remote_filename, progress_callback=None):
        """
        Upload file local len server vao folder cua user.
        Server se luu vao storage/<user_id>/<remote_filename>
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(local_path)

        file_size = os.path.getsize(local_path)
        url = f"{self.server_url}/api/storage/upload"

        # Su dung streaming upload de khong dung het RAM voi file lon
        with open(local_path, "rb") as f:
            files = {"file": (remote_filename, f, "application/octet-stream")}
            data = {"filename": remote_filename, "size": str(file_size)}

            print(f"[storage] Uploading {remote_filename} ({file_size:,} bytes)...")
            response = self.session.post(
                url,
                headers=self._headers(),
                files=files,
                data=data,
                timeout=self.upload_timeout
            )

        if response.status_code != 200:
            raise RuntimeError(f"Upload failed: {response.status_code} {response.text}")

        result = response.json()
        print(f"[storage] Upload OK: {result}")
        return result

    def download(self, remote_filename, local_path, progress_callback=None):
        """Tai file backup tu server ve agent"""
        url = f"{self.server_url}/api/storage/download"
        params = {"filename": remote_filename}

        print(f"[storage] Downloading {remote_filename} -> {local_path}")
        with self.session.get(
            url, headers=self._headers(), params=params,
            stream=True, timeout=self.download_timeout
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(f"Download failed: {response.status_code} {response.text}")

            total = int(response.headers.get("Content-Length", 0))
            written = 0
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=config.CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)
                        if progress_callback and total > 0:
                            progress_callback(int(written * 100 / total))

        print(f"[storage] Download OK: {written:,} bytes")
        return local_path

    def list_files(self):
        """Liet ke cac file trong folder cua user"""
        url = f"{self.server_url}/api/storage/list"
        response = self.session.get(url, headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json()

    def delete(self, remote_filename):
        """Xoa file backup tren server"""
        url = f"{self.server_url}/api/storage/delete"
        response = self.session.post(
            url, headers=self._headers(),
            json={"filename": remote_filename}, timeout=30
        )
        response.raise_for_status()
        return response.json()

    def ping(self):
        """Kiem tra ket noi den server"""
        try:
            response = self.session.get(f"{self.server_url}/api/ping", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
