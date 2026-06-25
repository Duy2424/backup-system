"""
Restore Logic - thuc hien restore tren agent
Quy trinh:
1. Tai file backup tu server (Win 2016) ve agent (Win 2012)
2. Giai ma file
3. Giai nen ra thu muc tam
4. Doc snapshot tu backup va tao snapshot hien tai
5. So sanh: file thieu -> them, file du -> xoa, file khac -> ghi de
6. Restore system state (network adapter, firewall, defender)
"""
# Auto-add shared/ to import path (cho phep import config, database, snapshot, encryption_utils)
import sys
import os
_SHARED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import os
import tarfile
import json
import shutil
from datetime import datetime

import config
import snapshot
import system_state
import encryption_utils
import sql_registry
from remote_storage import RemoteStorageClient

import platform
_IS_WINDOWS = platform.system() == "Windows"
_MAX_PATH = 250  # An toan duoi 260 (gioi han Windows)


def _safe_extractall(tar_path, extract_dir):
    """
    Giai nen tar an toan:
    - Xu ly duong dan qua dai (>260 ky tu tren Windows) bang prefix \\?\\
    - Bo qua file bi loi (permission, path invalid, v.v.)
    - Tra ve (so_file_bo_qua, so_file_ok)
    """
    skip_count = 0
    ok_count = 0

    def _long_path(p):
        """Them prefix de bypass gioi han 260 ky tu tren Windows"""
        if _IS_WINDOWS and len(p) > _MAX_PATH and not p.startswith("\\\\?\\"):
            return "\\\\?\\" + p.replace("/", "\\")
        return p

    with tarfile.open(tar_path, "r:gz") as tar:
        members = tar.getmembers()
        total = len(members)
        for i, member in enumerate(members):
            # Tinh duong dan dich
            dest = os.path.normpath(os.path.join(extract_dir, member.name))

            # Kiem tra path traversal attack
            if not dest.startswith(os.path.normpath(extract_dir)):
                skip_count += 1
                continue

            try:
                if member.isdir():
                    # Tao thu muc voi long path support
                    long_dest = _long_path(dest)
                    os.makedirs(long_dest, exist_ok=True)
                    ok_count += 1
                elif member.isfile():
                    # Tao thu muc cha
                    parent = os.path.dirname(dest)
                    long_parent = _long_path(parent)
                    os.makedirs(long_parent, exist_ok=True)

                    # Ghi file voi long path
                    long_dest = _long_path(dest)
                    with tar.extractfile(member) as src, \
                         open(long_dest, "wb") as dst:
                        while True:
                            chunk = src.read(65536)
                            if not chunk:
                                break
                            dst.write(chunk)
                    ok_count += 1
                else:
                    ok_count += 1  # symlink, etc - skip silently

            except (OSError, IOError, ValueError) as e:
                err_str = str(e)
                # Chi in warning neu khong phai loi path qua dai / permission
                if "errno 2" not in err_str.lower() and "permission" not in err_str.lower():
                    print(f"  [WARN extract] {member.name[:80]}: {e}")
                skip_count += 1

    return skip_count, ok_count



def perform_restore(user, backup_filename, progress_cb=None, dry_run=False):
    """
    Thuc hien restore.

    Args:
        user: dict thong tin user
        backup_filename: ten file backup tren server
        progress_cb: callable(percent, message)
        dry_run: neu True chi so sanh khong thuc su restore

    Returns:
        dict: { 'success', 'compare_result', 'system_diffs' }
    """
    def _progress(p, m):
        if progress_cb:
            progress_cb(p, m)
        print(f"[restore {p}%] {m}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = os.path.join(config.RESTORE_TEMP_DIR, f"restore_{timestamp}")
    os.makedirs(work_dir, exist_ok=True)

    try:
        # ===== BUOC 1: DOWNLOAD TU SERVER =====
        _progress(5, f"Dang tai backup tu server: {backup_filename}")
        client = RemoteStorageClient(config.SERVER_URL, user["token"])
        if not client.ping():
            raise ConnectionError(f"Khong ket noi duoc den server {config.SERVER_URL}")

        encrypted_path = os.path.join(work_dir, backup_filename)
        client.download(backup_filename, encrypted_path)
        _progress(25, f"Tai xong: {os.path.getsize(encrypted_path):,} bytes")

        # ===== BUOC 2: GIAI MA =====
        _progress(30, "Dang giai ma AES-256...")
        tar_path = os.path.join(work_dir, "archive.tar.gz")
        encryption_utils.decrypt_file(encrypted_path, tar_path, user["encryption_key"])
        _progress(45, f"Giai ma xong: {os.path.getsize(tar_path):,} bytes")

        # ===== BUOC 3: GIAI NEN =====
        _progress(50, "Dang giai nen...")
        extract_dir = os.path.join(work_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        skip_count, ok_count = _safe_extractall(tar_path, extract_dir)
        _progress(60, f"Giai nen xong: {ok_count} files OK, {skip_count} files bo qua (path qua dai/bi lock)")

        # ===== BUOC 4: DOC METADATA & SYSTEM STATE =====
        meta_path = os.path.join(extract_dir, "_meta", "metadata.json")
        snap_path = os.path.join(extract_dir, "_meta", "snapshot.json")
        sys_state_path = os.path.join(extract_dir, "_meta", "system_state.json")

        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # Thanh phan co trong ban backup nay (ho tro backup chon loc).
        # Ban backup cu (khong co 'components') -> coi nhu day du.
        components = metadata.get("components")
        do_files = (components is None) or ("files" in components)

        backup_sys_state = {}
        if os.path.exists(sys_state_path):
            with open(sys_state_path, "r", encoding="utf-8") as f:
                backup_sys_state = json.load(f)

        comp_label = ", ".join(components) if components else "toan bo"
        _progress(65, f"Backup tu {metadata.get('created_at')} | Thanh phan: {comp_label}")

        # ===== BUOC 5: SO SANH FILE (chi khi backup co thanh phan 'files') =====
        compare_result = {
            "missing": [], "extra": [], "modified": [], "same": [],
            "summary": {"total_backup": 0, "total_current": 0,
                        "to_add": 0, "to_delete": 0, "to_overwrite": 0, "unchanged": 0},
        }
        backup_snap = None
        current_snap = None
        if do_files and os.path.exists(snap_path):
            _progress(70, "Tao snapshot hien tai de so sanh...")
            backup_snap = snapshot.load_snapshot(snap_path)
            current_snap = snapshot.create_snapshot(
                metadata.get("paths", []), exclude_patterns=config.EXCLUDE_PATTERNS
            )
            compare_result = snapshot.compare_snapshots(backup_snap, current_snap)
            summary = compare_result["summary"]
            _progress(75, f"So sanh xong: them={summary['to_add']}, "
                          f"xoa={summary['to_delete']}, ghi_de={summary['to_overwrite']}, "
                          f"giu_nguyen={summary['unchanged']}")
            print(f"\n  [SO SANH SNAPSHOT]")
            print(f"  - Backup: {summary['total_backup']} files | Hien tai: {summary['total_current']} files")
            print(f"  - Them={summary['to_add']} Xoa={summary['to_delete']} "
                  f"GhiDe={summary['to_overwrite']} GiuNguyen={summary['unchanged']}")
        else:
            _progress(75, "Bo qua so sanh file (ban backup khong co thanh phan 'files').")

        # So sanh system state (chi cac thanh phan co trong backup)
        sys_diffs = []
        if backup_sys_state:
            current_sys_state = system_state.capture_system_state()
            sys_diffs = system_state.compare_system_state(backup_sys_state, current_sys_state)
            if sys_diffs:
                print(f"\n  [SYSTEM STATE DIFFS]")
                for d in sys_diffs:
                    print(f"  - {d}")

        if dry_run:
            _progress(100, "Dry run - khong thuc hien restore")
            shutil.rmtree(work_dir, ignore_errors=True)
            return {
                "success": True, "dry_run": True,
                "compare_result": compare_result, "system_diffs": sys_diffs,
                "components": components,
            }

        # ===== BUOC 6: RESTORE SQL + REGISTRY (neu co trong ban backup) =====
        sql_dir = os.path.join(extract_dir, "_sql")
        if os.path.exists(sql_dir):
            bak_files = [f for f in os.listdir(sql_dir) if f.endswith(".bak")]
            if bak_files:
                _progress(76, f"Dang restore {len(bak_files)} SQL database(s)...")
                for bak_file in bak_files:
                    sql_registry.restore_sql_database(
                        os.path.join(sql_dir, bak_file), os.path.splitext(bak_file)[0])

        reg_dir = os.path.join(extract_dir, "_registry")
        if os.path.exists(reg_dir) and os.listdir(reg_dir):
            _progress(78, "Dang restore Windows Registry...")
            sql_registry.restore_registry(reg_dir)

        # ===== BUOC 7: AP DUNG THAY DOI FILE (chi khi co thanh phan 'files') =====
        if do_files and backup_snap is not None and current_snap is not None:
            _progress(80, "Dang xoa file du...")
            for rel in compare_result["extra"]:
                info = current_snap["files"].get(rel)
                if info and info.get("abs_path"):
                    try:
                        os.remove(info["abs_path"])
                        print(f"  [XOA] {info['abs_path']}")
                    except OSError as e:
                        print(f"  [WARN] Khong xoa duoc {info['abs_path']}: {e}")

            _progress(85, "Dang ghi de file khac noi dung va them file thieu...")
            data_dir = os.path.join(extract_dir, "_data")
            for rel in compare_result["modified"] + compare_result["missing"]:
                backup_info = backup_snap["files"].get(rel)
                if not backup_info:
                    continue
                src = os.path.normpath(os.path.join(data_dir, rel))
                if not os.path.exists(src):
                    print(f"  [WARN] File backup khong tim thay: {src}")
                    continue
                dst = backup_info.get("abs_path")
                if not dst:
                    continue
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    action = "GHI DE" if rel in compare_result["modified"] else "THEM"
                    print(f"  [{action}] {dst}")
                except OSError as e:
                    print(f"  [WARN] Khong ghi duoc {dst}: {e}")
        else:
            _progress(85, "Bo qua khoi phuc file (ban backup khong co thanh phan 'files').")

        # Don dep file tam (system state da nam trong RAM nen van restore duoc sau khi xoa)
        shutil.rmtree(work_dir, ignore_errors=True)

        # ===== BUOC 8: BAO 100% TRUOC KHI RESTORE NETWORK =====
        # QUAN TRONG: bao 100% TRUOC khi doi IP/firewall vi doi mang se cat ket noi.
        _progress(100, "RESTORE HOAN TAT! Dang ap dung system state...")

        # ===== BUOC 9: RESTORE SYSTEM STATE (chi thanh phan co trong backup) =====
        if backup_sys_state:
            print("[restore] Khoi phuc system state (chi thanh phan da backup)...")
            system_state.restore_system_state(backup_sys_state)
            print("[restore] System state da duoc khoi phuc!")

        return {
            "success": True,
            "compare_result": compare_result,
            "system_diffs": sys_diffs,
            "components": components,
            "backup_date": metadata.get("created_at"),
        }

    except Exception as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
