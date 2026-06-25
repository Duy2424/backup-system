"""
Agent - chay tren Windows Server 2012 (client)
Chuc nang:
- Poll web server (Win 2016) de lay job
- Khi co job backup -> goi backup_logic
- Khi co job restore -> goi restore_logic
- Bao tien do va ket qua ve server

Chay: python agent.py
"""
# Auto-add shared/ to import path (cho phep import config, database, snapshot, encryption_utils)
import sys
import os
_SHARED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import os
import sys
import time
import json
import traceback
import requests

import config
import database
import backup_logic
import restore_logic
import folder_browser


# Header xac thuc gui kem moi request toi REST API cua server.
# Khop voi mo ta trong bao cao: "moi Request mang day du thong tin
# xac thuc thong qua header X-Auth-Token".
def _auth_headers():
    return {"X-Auth-Token": config.AGENT_TOKEN} if config.AGENT_TOKEN else {}


def update_job_progress(job_id, progress, message, status="running"):
    """Bao tien do job ve server"""
    try:
        requests.post(
            f"{config.SERVER_URL}/api/jobs/{job_id}/update",
            json={
                "progress": progress,
                "message": message,
                "status": status
            },
            headers=_auth_headers(),
            timeout=10
        )
    except Exception as e:
        print(f"[agent] Khong update duoc job: {e}")


def report_backup_complete(job_id, user, result, paths):
    """Bao server da backup xong de ghi vao bang backups"""
    comps = result.get("components", [])
    btype = "full" if set(comps) >= set(config.BACKUP_COMPONENTS) else "selected"
    try:
        requests.post(
            f"{config.SERVER_URL}/api/jobs/{job_id}/backup_done",
            json={
                "filename": result["filename"],
                "size": result["size"],
                "snapshot_summary": result["snapshot_summary"],
                "paths": paths,
                "backup_type": btype,
                "components": comps
            },
            headers=_auth_headers(),
            timeout=30
        )
    except Exception as e:
        print(f"[agent] Khong bao server: {e}")


def handle_backup_job(job):
    """Xu ly job backup"""
    job_id = job["id"]
    user = job["_user"]
    params = job.get("params") or {}
    paths = params.get("paths")
    components = params.get("components")

    print(f"\n{'='*60}")
    print(f"[agent] BAT DAU BACKUP - Job #{job_id} - User: {user['username']}")
    print(f"  Paths: {paths or '(default)'}")
    print(f"  Components: {components or '(toan bo)'}")
    print(f"{'='*60}")

    def progress_cb(p, m):
        update_job_progress(job_id, p, m)

    try:
        result = backup_logic.perform_backup(user, paths=paths, components=components, progress_cb=progress_cb)
        # Bao server tao backup record
        report_backup_complete(job_id, user, result, paths or config.DEFAULT_BACKUP_PATHS)

        update_job_progress(job_id, 100, "Backup hoan tat!", status="completed")
        requests.post(
            f"{config.SERVER_URL}/api/jobs/{job_id}/update",
            json={"completed": True, "status": "completed"},
            headers=_auth_headers(),
            timeout=10
        )
        print(f"[agent] BACKUP THANH CONG - {result['filename']}")

    except Exception as e:
        err = f"Loi: {e}\n{traceback.format_exc()}"
        print(f"[agent] BACKUP LOI: {err}")
        update_job_progress(job_id, 0, str(e), status="failed")


def handle_restore_job(job):
    """Xu ly job restore"""
    job_id = job["id"]
    user = job["_user"]
    params = job.get("params") or {}
    filename = params.get("filename")

    print(f"\n{'='*60}")
    print(f"[agent] BAT DAU RESTORE - Job #{job_id} - User: {user['username']}")
    print(f"  File: {filename}")
    print(f"{'='*60}")

    if not filename:
        update_job_progress(job_id, 0, "Khong co filename", status="failed")
        return

    # QUAN TRONG: Khi tien do dat 100%, cap nhat ngay TRUOC khi restore network
    # Vi restore network se cat mang -> khong bao duoc server nua -> job mac 90%
    def progress_cb(p, m):
        update_job_progress(job_id, p, m)
        if p >= 100:
            # Bao completed ngay luoc luon (truoc khi mang bi ngat)
            try:
                requests.post(
                    f"{config.SERVER_URL}/api/jobs/{job_id}/update",
                    json={"status": "completed", "progress": 100,
                          "message": m, "completed": True},
                    headers=_auth_headers(),
                    timeout=5
                )
                print(f"[agent] Da bao completed len server truoc khi doi mang")
            except Exception as ex:
                print(f"[agent] Khong bao duoc (mang da doi): {ex}")

    try:
        result = restore_logic.perform_restore(user, filename, progress_cb=progress_cb)
        summary = result.get("compare_result", {}).get("summary", {})
        msg = (f"Restore xong! Them={summary.get('to_add', 0)}, "
               f"Xoa={summary.get('to_delete', 0)}, "
               f"Ghi de={summary.get('to_overwrite', 0)}")
        sys_diffs = result.get("system_diffs", [])
        if sys_diffs:
            msg += f". System: {len(sys_diffs)} thay doi da khoi phuc."
        print(f"[agent] RESTORE THANH CONG - {msg}")

    except Exception as e:
        err = f"Loi: {e}\n{traceback.format_exc()}"
        print(f"[agent] RESTORE LOI: {err}")
        update_job_progress(job_id, 0, str(e), status="failed")


def main_loop():
    """Vong lap chinh: poll server lay job"""
    print(f"\n[agent] Ket noi den server: {config.SERVER_URL}")

    # Ping kiem tra
    while True:
        try:
            r = requests.get(f"{config.SERVER_URL}/api/ping", timeout=5)
            if r.status_code == 200:
                print(f"[agent] Server OK: {r.json()}")
                break
        except Exception as e:
            print(f"[agent] Cho server... ({e})")
            time.sleep(3)

    print(f"[agent] Bat dau poll job moi {config.AGENT_POLL_INTERVAL} giay")
    print("="*60)

    last_status_print = 0
    while True:
        try:
            r = requests.get(
                f"{config.SERVER_URL}/api/jobs/poll",
                headers=_auth_headers(),
                timeout=10
            )
            if r.status_code == 401:
                print("[agent] LOI XAC THUC: AGENT_TOKEN khong hop le. "
                      "Sua agent_config.txt (lay token tu trang Admin).")
                time.sleep(10)
                continue
            if r.status_code == 200:
                data = r.json()
                job = data.get("job")
                if job:
                    job_type = job.get("job_type")
                    if job_type == "backup":
                        handle_backup_job(job)
                    elif job_type == "restore":
                        handle_restore_job(job)
                    else:
                        print(f"[agent] Job type khong ho tro: {job_type}")
            # In trang thai moi 30s neu khong co job
            now = time.time()
            if now - last_status_print > 30:
                print(f"[agent] Cho job... ({time.strftime('%H:%M:%S')})")
                last_status_print = now

        except requests.exceptions.RequestException as e:
            print(f"[agent] Loi ket noi: {e}, thu lai sau...")
            time.sleep(5)
        except Exception as e:
            print(f"[agent] Loi: {e}")
            traceback.print_exc()

        time.sleep(config.AGENT_POLL_INTERVAL)


if __name__ == "__main__":
    print("="*60)
    print("  BACKUP SYSTEM - AGENT")
    print("  Chay tren Windows Server 2012 (client)")
    print(f"  Server URL: {config.SERVER_URL}")
    print("="*60)

    # Khoi dong folder browser mini-server (port 5001)
    # Cho phep web UI duyet thu muc cua may agent qua REST API
    folder_browser.start_browser_server()
    print(f"  [OK] Folder browser API: port {folder_browser.BROWSER_PORT}")
    print("="*60)

    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n[agent] Dung agent.")
        sys.exit(0)
