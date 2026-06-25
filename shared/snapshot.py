"""
Tao snapshot (manifest) cua file system - dung de:
1. Backup incremental (chi luu thay doi)
2. So sanh trang thai luc backup vs luc restore
3. Phat hien file thieu / du / khac noi dung
"""
import os
import hashlib
import json
from datetime import datetime


def hash_file(path, chunk_size=65536):
    """Tinh SHA-256 hash cua file"""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except (IOError, PermissionError):
        return None


def create_snapshot(paths, exclude_patterns=None):
    """
    Tao snapshot/manifest cua cac duong dan
    Tra ve dict: { relative_path: {abs_path, size, mtime, hash} }
    """
    exclude_patterns = exclude_patterns or []
    snapshot = {
        "created_at": datetime.now().isoformat(),
        "paths": paths,
        "files": {}
    }

    for base_path in paths:
        if not os.path.exists(base_path):
            continue

        if os.path.isfile(base_path):
            rel = os.path.basename(base_path)
            try:
                stat = os.stat(base_path)
                snapshot["files"][rel] = {
                    "base": base_path,
                    "abs_path": base_path,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "hash": hash_file(base_path),
                    "is_file": True
                }
            except OSError:
                pass
            continue

        # Walk directory
        base_path = os.path.abspath(base_path)
        base_name = os.path.basename(base_path)
        for root, dirs, files in os.walk(base_path):
            # Loai bo thu muc system
            dirs[:] = [d for d in dirs if not _should_exclude(d, exclude_patterns)]

            for fname in files:
                if _should_exclude(fname, exclude_patterns):
                    continue
                abs_path = os.path.join(root, fname)
                try:
                    stat = os.stat(abs_path)
                except OSError:
                    continue

                rel_to_base = os.path.relpath(abs_path, base_path)
                # Su dung "tag" la ten thu muc goc + relative path
                rel = os.path.join(base_name, rel_to_base).replace("\\", "/")

                snapshot["files"][rel] = {
                    "base": base_path,
                    "abs_path": abs_path,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "hash": hash_file(abs_path),
                    "is_file": True
                }

    snapshot["total_files"] = len(snapshot["files"])
    snapshot["total_size"] = sum(f.get("size", 0) for f in snapshot["files"].values())
    return snapshot


def _should_exclude(name, patterns):
    """
    Kiem tra co nen loai tru file/thu muc nay khong.
    Khop voi: ten chinh xac, substring, hoac extension (.tmp, .log...)
    """
    name_lower = name.lower()
    for p in patterns:
        p_lower = p.lower()
        # Khop chinh xac (case-insensitive)
        if name_lower == p_lower:
            return True
        # Khop extension (.tmp, .etl, ...)
        if p_lower.startswith(".") and name_lower.endswith(p_lower):
            return True
        # Khop prefix (~$ cho file Office lock)
        if p_lower.startswith("~") and name_lower.startswith(p_lower.lstrip("~")):
            if name_lower.startswith("~"):
                return True
        # Khop substring (cho path dai nhu Google\Chrome...)
        if p in name or p_lower in name_lower:
            return True
    return False


def compare_snapshots(backup_snap, current_snap):
    """
    So sanh 2 snapshot:
    - missing: file co trong backup nhung khong co hien tai (can them lai)
    - extra: file co hien tai nhung khong co trong backup (can xoa)
    - modified: file ton tai ca 2 nhung khac hash (can ghi de)
    - same: file giong nhau (khong can lam gi)
    """
    backup_files = set(backup_snap["files"].keys())
    current_files = set(current_snap["files"].keys())

    missing = backup_files - current_files
    extra = current_files - backup_files
    common = backup_files & current_files

    modified = set()
    same = set()
    for f in common:
        b_hash = backup_snap["files"][f].get("hash")
        c_hash = current_snap["files"][f].get("hash")
        if b_hash != c_hash:
            modified.add(f)
        else:
            same.add(f)

    return {
        "missing": list(missing),
        "extra": list(extra),
        "modified": list(modified),
        "same": list(same),
        "summary": {
            "total_backup": len(backup_files),
            "total_current": len(current_files),
            "to_add": len(missing),
            "to_delete": len(extra),
            "to_overwrite": len(modified),
            "unchanged": len(same)
        }
    }


def save_snapshot(snapshot, path):
    """Luu snapshot ra file JSON"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)


def load_snapshot(path):
    """Doc snapshot tu file JSON"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    snap = create_snapshot(["/tmp"])
    print(f"Total files: {snap['total_files']}, Total size: {snap['total_size']}")
