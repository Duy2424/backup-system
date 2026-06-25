"""
Backup Logic - thuc hien backup tren agent (Win 2012)

Quy trinh day du:
1. Tao snapshot (manifest SHA-256) cua tat ca file
2. Capture system state: network adapter, firewall, defender
3. Backup SQL Server databases (neu co)
4. Backup Windows Registry keys quan trong
5. Dong goi tat ca thanh 1 file tar.gz
6. Ma hoa AES-256
7. Upload len server (Win 2016) vao folder rieng cua user
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


def perform_backup(user, paths=None, backup_type="full", components=None, progress_cb=None):
    """
    Thuc hien backup (ho tro backup CHON LOC theo thanh phan).

    Args:
        user: dict thong tin user
        paths: list duong dan can backup (chi dung khi co thanh phan 'files')
        backup_type: 'full' hoac 'selected'
        components: list thanh phan can backup (xem config.BACKUP_COMPONENTS).
                    None = backup toan bo (full).
        progress_cb: callable(percent, message)

    Returns:
        dict: { success, filename, size, components, snapshot_summary }
    """
    def _progress(p, m):
        if progress_cb:
            progress_cb(p, m)
        print(f"[backup {p:3d}%] {m}")

    # ----- Chuan hoa danh sach thanh phan -----
    if components is None:
        components = list(config.BACKUP_COMPONENTS)
    components = [c for c in components if c in config.BACKUP_COMPONENTS]
    if not components:
        components = list(config.BACKUP_COMPONENTS)
    do_files = "files" in components
    is_full = set(components) >= set(config.BACKUP_COMPONENTS)
    backup_type = "full" if is_full else "selected"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{user['username']}_{timestamp}"
    work_dir = os.path.join(config.BACKUP_TEMP_DIR, backup_name)
    os.makedirs(work_dir, exist_ok=True)

    _progress(2, f"Bat dau backup ({'toan bo' if is_full else 'chon loc'}): {', '.join(components)}")

    try:
        snap = None
        snap_path = None
        used_paths = []

        # ===== BUOC 1: SNAPSHOT (chi khi co thanh phan 'files') =====
        if do_files:
            paths = paths or config.DEFAULT_BACKUP_PATHS
            paths = [p for p in paths if os.path.exists(p)]
            if not paths:
                _progress(0, f"CANH BAO: Duong dan khong ton tai: {config.DEFAULT_BACKUP_PATHS}")
                sample = os.path.join(config.BASE_DIR, "agent", "sample_data")
                if not os.path.exists(sample):
                    sample = os.path.join(config.BASE_DIR, "sample_data")
                if os.path.exists(sample):
                    paths = [sample]
                    _progress(0, "Su dung thu muc sample_data thay the...")
                else:
                    raise ValueError("Khong co duong dan nao ton tai de backup")
            used_paths = paths
            _progress(5, "Dang tao snapshot (quet va hash tat ca file)...")
            snap = snapshot.create_snapshot(paths, exclude_patterns=config.EXCLUDE_PATTERNS)
            snap_path = os.path.join(work_dir, "snapshot.json")
            snapshot.save_snapshot(snap, snap_path)
            local_snap = os.path.join(config.SNAPSHOTS_DIR, f"user_{user['id']}_latest.json")
            snapshot.save_snapshot(snap, local_snap)
            _progress(15, f"Snapshot xong: {snap['total_files']} files, {snap['total_size'] / 1024 / 1024:.2f} MB")
        else:
            _progress(15, "Bo qua backup file (khong tick thanh phan 'files').")

        # ===== BUOC 2: SYSTEM STATE (loc theo thanh phan da chon) =====
        _progress(20, "Dang capture system state...")
        full_state = system_state.capture_system_state()
        sys_st = _select_system_state(full_state, components)
        sys_st_path = os.path.join(work_dir, "system_state.json")
        with open(sys_st_path, "w", encoding="utf-8") as f:
            json.dump(sys_st, f, indent=2, ensure_ascii=False, default=str)
        _log_state_summary(sys_st, _progress)

        # ===== BUOC 3+4: SQL + REGISTRY (chi khi backup toan bo) =====
        bak_files = []
        reg_files = []
        reg_dir = os.path.join(work_dir, "registry")
        if is_full:
            _progress(25, "Dang kiem tra va backup SQL Server...")
            sql_dir = os.path.join(work_dir, "sql_backups")
            if sql_registry.has_sql_server():
                bak_files = sql_registry.backup_all_sql(sql_dir)
                _progress(35, f"  SQL backup xong: {len(bak_files)} database(s)")
            else:
                _progress(28, "  Khong co SQL Server, bo qua")
            _progress(38, "Dang backup Windows Registry...")
            reg_files = sql_registry.backup_registry(reg_dir)
            _progress(42, f"  Registry backup xong: {len(reg_files)} keys")
        else:
            _progress(42, "Backup chon loc - bo qua SQL Server & Registry.")

        # ===== BUOC 5: NEN =====
        _progress(45, "Dang nen tat ca vao 1 file tar.gz...")
        tar_path = os.path.join(work_dir, "archive.tar.gz")
        with tarfile.open(tar_path, "w:gz", compresslevel=6) as tar:
            meta = {
                "user_id": user["id"],
                "username": user["username"],
                "created_at": datetime.now().isoformat(),
                "backup_type": backup_type,
                "components": components,
                "paths": used_paths,
                "version": "2.1",
                "has_files": do_files,
                "has_sql": len(bak_files) > 0,
                "has_registry": len(reg_files) > 0,
            }
            meta_path = os.path.join(work_dir, "metadata.json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            tar.add(meta_path, arcname="_meta/metadata.json")
            tar.add(sys_st_path, arcname="_meta/system_state.json")
            if do_files and snap_path:
                tar.add(snap_path, arcname="_meta/snapshot.json")

            for bak in bak_files:
                tar.add(bak, arcname=f"_sql/{os.path.basename(bak)}")
            if is_full and os.path.exists(reg_dir):
                for rf in os.listdir(reg_dir):
                    tar.add(os.path.join(reg_dir, rf), arcname=f"_registry/{rf}")

            if do_files and snap:
                total_files = len(snap["files"])
                _progress(50, f"Dang nen {total_files} files...")
                for i, (rel_path, info) in enumerate(snap["files"].items()):
                    abs_path = info.get("abs_path")
                    if abs_path and os.path.exists(abs_path):
                        try:
                            tar.add(abs_path, arcname=f"_data/{rel_path}")
                        except (PermissionError, OSError) as e:
                            print(f"  [WARN] Bo qua (bi lock hoac loi): {abs_path[:60]}... -> {e}")
                    if i % 100 == 0 and total_files > 0:
                        pct = 50 + int(20 * i / total_files)
                        _progress(pct, f"  Nen file {i:,}/{total_files:,}")

        tar_size = os.path.getsize(tar_path)
        _progress(70, f"Nen xong: {tar_size / 1024 / 1024:.2f} MB")

        # ===== BUOC 6: MA HOA =====
        _progress(75, "Dang ma hoa AES-256...")
        enc_filename = f"{backup_name}.bkup"
        enc_path = os.path.join(work_dir, enc_filename)
        encryption_utils.encrypt_file(tar_path, enc_path, user["encryption_key"])
        enc_size = os.path.getsize(enc_path)
        _progress(82, f"Ma hoa xong: {enc_size / 1024 / 1024:.2f} MB")

        # ===== BUOC 7: UPLOAD =====
        _progress(85, f"Dang upload len server ({config.SERVER_URL})...")
        client = RemoteStorageClient(config.SERVER_URL, user["token"])
        if not client.ping():
            raise ConnectionError(f"Khong ket noi duoc den server {config.SERVER_URL}")
        result = client.upload(enc_path, enc_filename)
        _progress(95, f"Upload xong: {enc_size / 1024 / 1024:.2f} MB da len server")

        shutil.rmtree(work_dir, ignore_errors=True)
        _progress(100, f"BACKUP HOAN TAT! File: {enc_filename} ({enc_size / 1024 / 1024:.2f} MB)")

        return {
            "success": True,
            "filename": enc_filename,
            "size": enc_size,
            "components": components,
            "snapshot_summary": {
                "total_files": snap["total_files"] if snap else 0,
                "total_size": snap["total_size"] if snap else 0,
                "components": components,
            },
            "remote_path": result.get("path"),
        }

    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def _select_system_state(full_state, components):
    """Loc system_state day du -> chi giu cac thanh phan da tick chon.
    Khong them key cho thanh phan KHONG chon, de luc restore tu dong bo qua
    (restore_system_state / restore_network_advanced chi restore key co mat).
    """
    sel = {
        "platform": full_state.get("platform"),
        "hostname": full_state.get("hostname"),
        "components": list(components),
    }

    # IPv4 / IPv6 nam chung trong adapters
    if "ipv4" in components or "ipv6" in components:
        adapters = []
        for a in full_state.get("adapters", []):
            a2 = {
                "name": a.get("name"), "mac": a.get("mac"),
                "status": a.get("status"), "index": a.get("index"),
                "mode": a.get("mode"),
            }
            if "ipv4" in components:
                v4 = a.get("ipv4") or {}
                a2["ipv4"] = v4
                # Tuong thich nguoc: code restore cu doc field IPv4 o cap goc
                a2.update({
                    "ip": v4.get("ip"), "prefix": v4.get("prefix"),
                    "subnet_mask": v4.get("subnet_mask"), "gateway": v4.get("gateway"),
                    "dns": v4.get("dns"), "dhcp": v4.get("dhcp"),
                })
            if "ipv6" in components:
                a2["ipv6"] = a.get("ipv6") or {}
            adapters.append(a2)
        sel["adapters"] = adapters

    if "firewall" in components:
        sel["firewall"] = full_state.get("firewall", {})
    if "defender" in components:
        sel["defender"] = full_state.get("defender", {})

    na_full = full_state.get("network_advanced", {}) or {}
    na = {}
    if "route" in components:
        na["routing_table"] = na_full.get("routing_table", [])
    if "hosts" in components:
        na["hosts_file"] = na_full.get("hosts_file", "")
    if "firewall" in components:
        na["firewall_rules"] = na_full.get("firewall_rules", [])
    if "shares" in components:
        na["network_shares"] = na_full.get("network_shares", [])
    if "portproxy" in components:
        na["port_proxy"] = na_full.get("port_proxy", [])
    if na:
        sel["network_advanced"] = na

    return sel


def _log_state_summary(sys_st, _progress):
    """Log kieu demo cac thanh phan system state da capture (chi cai co mat)."""
    for a in sys_st.get("adapters", []):
        v4 = a.get("ipv4", {}) or {}
        v6 = a.get("ipv6", {}) or {}
        _progress(20, f"  Adapter: {a.get('name')} | Mode={a.get('mode')}")
        if v4.get("ip"):
            _progress(20, f"    IPv4: {v4.get('ip')}/{v4.get('prefix')} gw={v4.get('gateway')} dns={v4.get('dns')}")
        if v6.get("ip"):
            _progress(20, f"    IPv6: {v6.get('ip')}/{v6.get('prefix')} gw={v6.get('gateway')}")
    for prof, st in sys_st.get("firewall", {}).items():
        _progress(20, f"  Firewall {prof}: enabled={st.get('enabled')}")
    if "defender" in sys_st:
        _progress(20, f"  Defender: realtime={sys_st['defender'].get('realtime_enabled')}")
    na = sys_st.get("network_advanced", {})
    if "routing_table" in na:
        _progress(22, f"  Routing table: {len(na.get('routing_table', []))} route(s)")
    if "firewall_rules" in na:
        _progress(22, f"  Firewall rules: {len(na.get('firewall_rules', []))} rule(s)")
    if "network_shares" in na:
        _progress(22, f"  Network shares: {len(na.get('network_shares', []))} share(s)")
    if "port_proxy" in na:
        _progress(22, f"  Port proxy: {len(na.get('port_proxy', []))} rule(s)")
    if "hosts_file" in na:
        _progress(22, f"  Hosts file: {len(na.get('hosts_file', ''))} bytes")


def _estimate_size(paths):
    """Uoc tinh tong size cua tat ca paths"""
    total = 0
    for p in paths:
        if os.path.isfile(p):
            try:
                total += os.path.getsize(p)
            except OSError:
                pass
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                # Loai bo thu muc bi exclude
                dirs[:] = [d for d in dirs if not any(
                    e in d for e in config.EXCLUDE_PATTERNS)]
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
    return total
