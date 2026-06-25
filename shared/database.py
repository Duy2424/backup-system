"""
Database SQLite - quan ly user, backup history, jobs, schedules
"""
import sqlite3
import hashlib
import secrets
import base64
import json
from datetime import datetime
from contextlib import contextmanager
import config


def hash_password(password, salt=None):
    """Hash password voi salt"""
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"


def verify_password(password, stored):
    """Kiem tra password"""
    try:
        salt, _ = stored.split("$")
        return hash_password(password, salt) == stored
    except Exception:
        return False


def generate_token():
    """Sinh token ngau nhien cho user"""
    return secrets.token_urlsafe(32)


def generate_encryption_key():
    """Sinh khoa ma hoa Fernet 32 byte tu secrets.token_bytes()
    (khop mo ta bao cao muc 2.4.4: "khoa Fernet 32 byte qua secrets.token_bytes()").
    Fernet yeu cau khoa la 32 byte ngau nhien duoc base64 urlsafe-encode."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


@contextmanager
def get_db():
    """Context manager cho ket noi DB"""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Khoi tao database (4 bang) va tao tai khoan admin mac dinh"""
    with get_db() as conn:
        cur = conn.cursor()

        # Bang users
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            token TEXT UNIQUE NOT NULL,
            encryption_key TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Bang backups - lich su backup
        cur.execute("""
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            drive_file_id TEXT,
            size INTEGER DEFAULT 0,
            backup_type TEXT DEFAULT 'full',
            paths TEXT,
            snapshot_summary TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        # Bang jobs - hang doi cong viec cho agent
        # Vong doi trang thai: pending -> running -> completed / failed
        cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            job_type TEXT NOT NULL,
            params TEXT,
            backup_id INTEGER,
            status TEXT DEFAULT 'pending',
            progress INTEGER DEFAULT 0,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (backup_id) REFERENCES backups(id) ON DELETE SET NULL
        )
        """)

        # Bang schedules - lich backup tu dong
        # (tao ngay tai init_db de dung chuan voi mo ta trong bao cao - muc 3.1.7)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            schedule_type TEXT NOT NULL,
            interval_hours INTEGER DEFAULT 24,
            time_of_day TEXT DEFAULT '02:00',
            day_of_week INTEGER DEFAULT 0,
            backup_paths TEXT,
            enabled INTEGER DEFAULT 1,
            last_run TIMESTAMP,
            next_run TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        # Tao admin mac dinh
        cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO users (username, password, role, token, encryption_key) VALUES (?, ?, ?, ?, ?)",
                ("admin", hash_password("admin123"), "admin",
                 generate_token(), generate_encryption_key())
            )
            # Tao user demo
            cur.execute(
                "INSERT INTO users (username, password, role, token, encryption_key) VALUES (?, ?, ?, ?, ?)",
                ("user1", hash_password("user123"), "user",
                 generate_token(), generate_encryption_key())
            )

        conn.commit()


# === USER OPERATIONS ===

def get_user_by_username(username):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_token(token):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
        return dict(row) if row else None


def list_users():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, role, token, created_at FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def create_user(username, password, role="user"):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (username, password, role, token, encryption_key) VALUES (?, ?, ?, ?, ?)",
            (username, hash_password(password), role,
             generate_token(), generate_encryption_key())
        )


def update_user(user_id, username=None, password=None, role=None):
    with get_db() as conn:
        updates, params = [], []
        if username:
            updates.append("username=?"); params.append(username)
        if password:
            updates.append("password=?"); params.append(hash_password(password))
        if role:
            updates.append("role=?"); params.append(role)
        if updates:
            params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", params)


def delete_user(user_id):
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))


# === BACKUP OPERATIONS ===

def create_backup_record(user_id, filename, paths, backup_type="full"):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO backups (user_id, filename, paths, backup_type) VALUES (?, ?, ?, ?)",
            (user_id, filename, json.dumps(paths), backup_type)
        )
        return cur.lastrowid


def update_backup(backup_id, **kwargs):
    if not kwargs:
        return
    with get_db() as conn:
        cols = ", ".join(f"{k}=?" for k in kwargs.keys())
        params = list(kwargs.values()) + [backup_id]
        conn.execute(f"UPDATE backups SET {cols} WHERE id=?", params)


def list_backups(user_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM backups WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_backup(backup_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
        return dict(row) if row else None


# === JOB OPERATIONS ===

def create_job(user_id, job_type, params=None, backup_id=None):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (user_id, job_type, params, backup_id) VALUES (?, ?, ?, ?)",
            (user_id, job_type, json.dumps(params or {}), backup_id)
        )
        return cur.lastrowid


def get_next_job():
    """Lay job tiep theo (status=pending) cho agent xu ly"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE id=?",
                (datetime.now().isoformat(), row["id"])
            )
            return dict(row)
        return None


def update_job(job_id, **kwargs):
    if not kwargs:
        return
    with get_db() as conn:
        cols = ", ".join(f"{k}=?" for k in kwargs.keys())
        params = list(kwargs.values()) + [job_id]
        conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", params)


def get_job(job_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs(user_id, limit=20):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
