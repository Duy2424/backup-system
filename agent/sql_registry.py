"""
Backup SQL Server databases va Windows Registry
- SQL Server: dung sqlcmd hoac PowerShell de tao file .bak
- Registry: export cac key quan trong ra file .reg
"""
# Auto-add shared/ to import path (cho phep import config, database, snapshot, encryption_utils)
import sys
import os
_SHARED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import os
import subprocess
import platform
import json
import config

IS_WINDOWS = platform.system() == "Windows"


def _run_cmd(args, timeout=300):
    """Chay lenh va tra ve (stdout, returncode)"""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True,
            timeout=timeout, shell=True
        )
        return result.stdout + result.stderr, result.returncode
    except Exception as e:
        return str(e), -1


def _run_ps(script, timeout=300):
    """Chay PowerShell"""
    if not IS_WINDOWS:
        return "", 0
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy",
             "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout + result.stderr, result.returncode
    except Exception as e:
        return str(e), -1


# ===== SQL SERVER BACKUP =====

def has_sql_server():
    """Kiem tra co SQL Server khong"""
    if not IS_WINDOWS:
        return False
    out, rc = _run_ps("Get-Service -Name 'MSSQLSERVER','MSSQL*' -ErrorAction SilentlyContinue | Where-Object {$_.Status -eq 'Running'} | Select-Object -ExpandProperty Name")
    return bool(out.strip())


def list_sql_databases():
    """Liet ke cac database trong SQL Server"""
    if not IS_WINDOWS:
        return []
    script = f"""
    $query = "SELECT name FROM sys.databases WHERE name NOT IN ('master','tempdb','model','msdb') AND state_desc='ONLINE'"
    Invoke-Sqlcmd -ServerInstance "{config.SQL_SERVER_INSTANCE}" -Query $query -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty name
    """
    out, rc = _run_ps(script)
    if rc != 0 or not out.strip():
        # Thu dung sqlcmd
        out2, rc2 = _run_cmd(
            f'sqlcmd -S {config.SQL_SERVER_INSTANCE} -Q '
            f'"SELECT name FROM sys.databases WHERE name NOT IN (\'master\',\'tempdb\',\'model\',\'msdb\')" '
            f'-h -1 -W'
        )
        if rc2 == 0:
            return [l.strip() for l in out2.splitlines() if l.strip() and l.strip() != 'name']
        return []
    return [l.strip() for l in out.splitlines() if l.strip()]


def backup_sql_database(db_name, out_dir):
    """
    Backup 1 SQL database ra file .bak
    Tra ve duong dan file .bak neu thanh cong, None neu loi
    """
    if not IS_WINDOWS:
        print(f"[sql] (Skip non-Windows) Backup DB: {db_name}")
        return None

    os.makedirs(out_dir, exist_ok=True)
    bak_path = os.path.join(out_dir, f"{db_name}.bak").replace("\\", "\\\\")

    # Dung T-SQL BACKUP DATABASE
    query = (
        f"BACKUP DATABASE [{db_name}] "
        f"TO DISK=N'{bak_path}' "
        f"WITH NOFORMAT, NOINIT, NAME=N'{db_name}-Full', "
        f"SKIP, NOREWIND, NOUNLOAD, STATS=10"
    )

    # Thu PowerShell Invoke-Sqlcmd
    ps_script = f'Invoke-Sqlcmd -ServerInstance "{config.SQL_SERVER_INSTANCE}" -Query "{query}" -QueryTimeout 600 -ErrorAction Stop'
    out, rc = _run_ps(ps_script, timeout=600)
    if rc == 0:
        real_path = bak_path.replace("\\\\", "\\")
        if os.path.exists(real_path):
            size = os.path.getsize(real_path)
            print(f"[sql] Backup {db_name} -> {real_path} ({size:,} bytes)")
            return real_path

    # Fallback: dung sqlcmd.exe
    real_bak = os.path.join(out_dir, f"{db_name}.bak")
    cmd = (
        f'sqlcmd -S {config.SQL_SERVER_INSTANCE} '
        f'-Q "BACKUP DATABASE [{db_name}] TO DISK=\'{real_bak}\' '
        f'WITH NOFORMAT, NOINIT, STATS=10"'
    )
    out2, rc2 = _run_cmd(cmd, timeout=600)
    if os.path.exists(real_bak):
        size = os.path.getsize(real_bak)
        print(f"[sql] Backup {db_name} (sqlcmd) -> {real_bak} ({size:,} bytes)")
        return real_bak

    print(f"[sql] WARN: Backup {db_name} that bai:\n{out}\n{out2}")
    return None


def backup_all_sql(out_dir):
    """
    Backup tat ca SQL databases
    Tra ve list cac file .bak da tao
    """
    if not IS_WINDOWS:
        return []

    # Lay danh sach DB tu config hoac tu dong detect
    databases = config.SQL_DATABASES
    if not databases:
        print("[sql] Auto-detect SQL databases...")
        databases = list_sql_databases()

    if not databases:
        print("[sql] Khong co SQL Server hoac khong co database nao")
        return []

    print(f"[sql] Tim thay {len(databases)} database(s): {databases}")
    bak_files = []
    for db in databases:
        bak = backup_sql_database(db, out_dir)
        if bak:
            bak_files.append(bak)
    return bak_files


def restore_sql_database(bak_path, db_name=None):
    """Restore SQL database tu file .bak"""
    if not IS_WINDOWS:
        print(f"[sql] (Skip non-Windows) Restore: {bak_path}")
        return False

    if not db_name:
        db_name = os.path.splitext(os.path.basename(bak_path))[0]

    query = (
        f"RESTORE DATABASE [{db_name}] "
        f"FROM DISK=N'{bak_path}' "
        f"WITH FILE=1, REPLACE, STATS=10"
    )
    ps_script = f'Invoke-Sqlcmd -ServerInstance "{config.SQL_SERVER_INSTANCE}" -Query "{query}" -QueryTimeout 600 -ErrorAction Stop'
    out, rc = _run_ps(ps_script, timeout=600)
    if rc == 0:
        print(f"[sql] Restore {db_name} thanh cong")
        return True

    # Fallback sqlcmd
    cmd = f'sqlcmd -S {config.SQL_SERVER_INSTANCE} -Q "RESTORE DATABASE [{db_name}] FROM DISK=\'{bak_path}\' WITH REPLACE"'
    out2, rc2 = _run_cmd(cmd, timeout=600)
    if rc2 == 0:
        print(f"[sql] Restore {db_name} (sqlcmd) thanh cong")
        return True

    print(f"[sql] WARN: Restore {db_name} that bai")
    return False


# ===== WINDOWS REGISTRY BACKUP =====

REGISTRY_KEYS = [
    # Cac key quan trong cua Windows
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    r"HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion",
    r"HKEY_CURRENT_USER\SOFTWARE",
    r"HKEY_CURRENT_USER\Control Panel",
]


def backup_registry(out_dir):
    """Export registry keys quan trong ra file .reg"""
    if not IS_WINDOWS:
        print("[registry] (Skip non-Windows)")
        return []

    os.makedirs(out_dir, exist_ok=True)
    reg_files = []

    for i, key in enumerate(REGISTRY_KEYS):
        safe_name = key.replace("\\", "_").replace(":", "")
        out_path = os.path.join(out_dir, f"reg_{i:02d}_{safe_name[:50]}.reg")
        cmd = f'reg export "{key}" "{out_path}" /y'
        out, rc = _run_cmd(cmd, timeout=60)
        if rc == 0 and os.path.exists(out_path):
            size = os.path.getsize(out_path)
            print(f"[registry] Export {key} -> {size:,} bytes")
            reg_files.append(out_path)
        else:
            print(f"[registry] WARN: Export {key} that bai: {out[:100]}")

    print(f"[registry] Tong: {len(reg_files)}/{len(REGISTRY_KEYS)} keys da export")
    return reg_files


def restore_registry(reg_dir):
    """Import lai cac file .reg"""
    if not IS_WINDOWS:
        print("[registry] (Skip non-Windows)")
        return

    if not os.path.exists(reg_dir):
        return

    reg_files = sorted(f for f in os.listdir(reg_dir) if f.endswith(".reg"))
    for fname in reg_files:
        fpath = os.path.join(reg_dir, fname)
        cmd = f'reg import "{fpath}"'
        out, rc = _run_cmd(cmd, timeout=30)
        if rc == 0:
            print(f"[registry] Import {fname} OK")
        else:
            print(f"[registry] WARN: Import {fname} that bai: {out[:100]}")


if __name__ == "__main__":
    print(f"SQL Server co san: {has_sql_server()}")
    print(f"Databases: {list_sql_databases()}")
