"""
Cau hinh chung cho he thong backup
"""
import os
import platform

# BASE_DIR la THU MUC GOC cua repo (parent cua shared/)
# Cau truc: <repo>/shared/config.py  ->  BASE_DIR = <repo>
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(_THIS_DIR) if os.path.basename(_THIS_DIR) == "shared" else _THIS_DIR
IS_WINDOWS = platform.system() == "Windows"

# Thu muc lam viec (chung cho ca server va agent)
WORK_DIR = os.path.join(BASE_DIR, "work")
BACKUP_TEMP_DIR = os.path.join(WORK_DIR, "backup_temp")
RESTORE_TEMP_DIR = os.path.join(WORK_DIR, "restore_temp")
SNAPSHOTS_DIR = os.path.join(WORK_DIR, "snapshots")
LOGS_DIR = os.path.join(WORK_DIR, "logs")

# Database (tren may server - Win 2016)
DB_PATH = os.path.join(BASE_DIR, "backup_system.db")

# Storage (tren may server - Win 2016)
STORAGE_DIR = os.path.join(BASE_DIR, "storage")

# Web server
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5000
SECRET_KEY = "doan-co-so-mang-may-tinh-2026-backup-system"

# ===== AGENT =====
SERVER_URL = os.environ.get("BACKUP_SERVER_URL", "http://192.168.10.1:5000")
# Token xac thuc cua agent khi goi REST API (header X-Auth-Token).
# Lay token nay tu trang Admin tren web UI (cot "Token" cua user).
AGENT_TOKEN = os.environ.get("BACKUP_AGENT_TOKEN", "")
# Tim agent_config.txt o nhieu vi tri:
# 1. <repo>/agent/agent_config.txt (cau truc moi)
# 2. <repo>/agent_config.txt        (cau truc cu)
_agent_cfg_candidates = [
    os.path.join(BASE_DIR, "agent", "agent_config.txt"),
    os.path.join(BASE_DIR, "agent_config.txt"),
]
for _agent_cfg in _agent_cfg_candidates:
    if os.path.exists(_agent_cfg):
        try:
            with open(_agent_cfg, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SERVER_URL="):
                        SERVER_URL = line.split("=", 1)[1].strip()
                    elif line.startswith("AGENT_TOKEN="):
                        AGENT_TOKEN = line.split("=", 1)[1].strip()
            break
        except Exception:
            pass

AGENT_POLL_INTERVAL = 3

# ===== BACKUP PATHS =====
# Cac duong dan se duoc backup tren may client (Win 2012)
# sample_data co the nam o <repo>/agent/sample_data (cau truc moi) hoac <repo>/sample_data (cu)
_sample_candidates = [
    os.path.join(BASE_DIR, "agent", "sample_data"),
    os.path.join(BASE_DIR, "sample_data"),
]
_sample_data = next((p for p in _sample_candidates if os.path.exists(p)), _sample_candidates[0])

if IS_WINDOWS:
    DEFAULT_BACKUP_PATHS = [
        r"C:\Users\Administrator",          # Du lieu user chinh
        r"C:\Users\Public",                 # Du lieu dung chung
        _sample_data,                       # Du lieu mau demo
    ]

    # Thu muc them tuy chon (uncomment de them)
    # DEFAULT_BACKUP_PATHS += [
    #     r"C:\Program Files\YourApp",      # Ung dung cu the
    #     r"C:\inetpub\wwwroot",            # IIS web files
    #     r"C:\Data",                       # Thu muc du lieu rieng
    # ]

    # Thu muc SQL backup tam (sqlcmd se export vao day truoc khi nen)
    SQL_BACKUP_TEMP = os.path.join(WORK_DIR, "sql_backups")
else:
    # Chay tren Linux (demo/test)
    DEFAULT_BACKUP_PATHS = [_sample_data]
    SQL_BACKUP_TEMP = os.path.join(WORK_DIR, "sql_backups")

# SQL Server cau hinh (neu co SQL Server)
# De trong neu khong co SQL Server
SQL_SERVER_INSTANCE = os.environ.get("SQL_INSTANCE", "localhost")
SQL_DATABASES = []  # VD: ["AdventureWorks", "MyDB"] - de trong neu khong co

# Loai tru file/folder khong can backup
# Pattern loai tru - khop voi TEN THU MUC hoac TEN FILE don le
EXCLUDE_DIRS = [
    # He thong
    "__pycache__", ".git", "node_modules",
    "work", "storage",
    # Windows temp - ten thu muc don le
    "Temp", "temp", "TMP", "tmp",
    "LocalLow", "INetCache", "INetCookies",
    "Temporary Internet Files",
    "CryptnetUrlCache", "PackageCache",
    "$Recycle.Bin", "$RECYCLE.BIN",
    "Windows.old", "MSOCache",
    "System Volume Information",
    # Phan mem
    "Cache", "CachedData",  # Browser cache dirs
    # AppData sub-folders khong can backup (Windows Store, cache, log)
    "Packages",          # Windows Store apps - rat nang, khong can
    "PackageCache",      # Visual Studio package cache
    "LocalState",        # App local state (thuong khong quan trong)
    "AC",                # AppCompat cache
    "Wer",               # Windows Error Reporting
    "CrashDumps",        # Crash dumps
    "SquirrelTemp",      # Electron app installer
    "npm-cache",         # Node.js cache
    "pip", "pip3",       # Python pip cache
    ".vs",               # Visual Studio solution files
]

# Pattern loai tru file (extension hoac prefix)
EXCLUDE_FILE_PATTERNS = [
    # File temp
    ".tmp", ".TMP", ".temp",
    # File lock Office (~$)
    "~$",
    # File he thong Windows
    "pagefile.sys", "hiberfil.sys", "swapfile.sys",
    "Thumbs.db", "desktop.ini",
    # Database tu code
    "backup_system.db", "agent_config.txt",
    # Log co the lon
    ".etl",
    # Windows Registry hive files - LUON BI LOCK khi OS dang chay
    # (da duoc backup rieng bang reg export roi)
    "NTUSER.DAT", "ntuser.dat",
    "ntuser.dat.LOG1", "ntuser.dat.LOG2",
    "UsrClass.dat",
    "UsrClass.dat.LOG1", "UsrClass.dat.LOG2",
    ".LOG1", ".LOG2",   # Registry transaction logs
    ".regtrans-ms",     # Registry transaction
    # Windows event log (co the rat lon)
    ".evtx",
]

# Gop chung de tuong thich nguoc voi code cu
EXCLUDE_PATTERNS = EXCLUDE_DIRS + EXCLUDE_FILE_PATTERNS

CHUNK_SIZE = 1024 * 1024  # 1MB

# Tao thu muc
for d in [WORK_DIR, BACKUP_TEMP_DIR, RESTORE_TEMP_DIR,
          SNAPSHOTS_DIR, LOGS_DIR, STORAGE_DIR, SQL_BACKUP_TEMP]:
    os.makedirs(d, exist_ok=True)
