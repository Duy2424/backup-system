"""
Web Server - chay tren Windows Server 2016
Chuc nang:
- Web UI cho user login, backup, restore, xem lich su
- Admin UI quan ly user (CRUD)
- REST API cho agent (poll job, upload/download file backup) - co xac thuc X-Auth-Token
- Storage: moi user co folder rieng storage/<user_id>/

Chay: python server.py
Mac dinh lang nghe 0.0.0.0:5000
"""
# Auto-add shared/ to import path (cho phep import config, database, snapshot, encryption_utils)
import sys
import os
_SHARED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import json
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, send_file, abort, flash
)
from werkzeug.utils import secure_filename

import config
import database
import scheduler
import requests as _requests


app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024 * 1024  # 10GB

# ===== HELPERS =====

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Ban khong co quyen truy cap.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


def current_user():
    if "user_id" not in session:
        return None
    return database.get_user_by_id(session["user_id"])


def user_storage_dir(user_id):
    """Folder rieng cua moi user tren server"""
    d = os.path.join(config.STORAGE_DIR, f"user_{user_id}")
    os.makedirs(d, exist_ok=True)
    return d


def get_user_from_token():
    """Lay user tu header X-Auth-Token (dung cho API agent)"""
    token = request.headers.get("X-Auth-Token")
    if not token:
        return None
    return database.get_user_by_token(token)


def api_auth_required(f):
    """
    Decorator xac thuc cho REST API cua agent.
    Moi request tu agent phai mang header X-Auth-Token hop le.
    (Khop voi mo ta trong bao cao: "moi Request mang day du thong tin
     xac thuc thong qua header X-Auth-Token")
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_user_from_token()
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        request._api_user = user
        return f(*args, **kwargs)
    return wrapper


# ===== WEB UI ROUTES =====

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = database.get_user_by_username(username)
        if user and database.verify_password(password, user["password"]):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash(f"Xin chao {user['username']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Sai username hoac password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    backups = database.list_backups(user["id"])
    jobs = database.list_jobs(user["id"], limit=10)
    # Thong ke
    stats = {
        "total_backups": len(backups),
        "total_size": sum(b.get("size") or 0 for b in backups),
        "last_backup": backups[0]["created_at"] if backups else None
    }
    return render_template("dashboard.html",
                           user=user, backups=backups, jobs=jobs, stats=stats)


@app.route("/backup", methods=["POST"])
@login_required
def start_backup():
    """User click nut backup -> tao job cho agent"""
    user = current_user()
    backup_type = request.form.get("type", "full")
    selected_path = request.form.get("path", "").strip()

    params = {}
    if backup_type == "selected" and selected_path:
        # Kiem tra path co ton tai khong (chay tren may agent nen chi check format)
        params["paths"] = [selected_path]
    else:
        params["paths"] = None  # Dung default

    job_id = database.create_job(user["id"], "backup", params)
    flash(f"Da tao job backup #{job_id}. Agent se thuc hien trong vai giay...", "info")
    return redirect(url_for("dashboard"))


@app.route("/restore/<int:backup_id>", methods=["POST"])
@login_required
def start_restore(backup_id):
    """User click restore tu backup nao do"""
    user = current_user()
    backup = database.get_backup(backup_id)
    if not backup or backup["user_id"] != user["id"]:
        flash("Backup khong ton tai.", "danger")
        return redirect(url_for("dashboard"))
    if backup["status"] != "completed":
        flash("Backup chua hoan tat, khong the restore.", "warning")
        return redirect(url_for("dashboard"))

    job_id = database.create_job(
        user["id"], "restore",
        params={"filename": backup["filename"]},
        backup_id=backup_id
    )
    flash(f"Da tao job restore #{job_id} tu backup '{backup['filename']}'.", "info")
    return redirect(url_for("dashboard"))


@app.route("/job/<int:job_id>/status")
@login_required
def job_status(job_id):
    """API trang thai job (de UI poll)"""
    user = current_user()
    job = database.get_job(job_id)
    if not job or (job["user_id"] != user["id"] and user["role"] != "admin"):
        return jsonify({"error": "not_found"}), 404
    return jsonify(job)


@app.route("/jobs/recent")
@login_required
def jobs_recent():
    """API lay jobs gan day cho UI auto-refresh"""
    user = current_user()
    jobs = database.list_jobs(user["id"], limit=5)
    return jsonify(jobs)


# ===== ADMIN ROUTES =====

@app.route("/admin/users")
@admin_required
def admin_users():
    users = database.list_users()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/add", methods=["POST"])
@admin_required
def admin_add_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "user")
    if not username or not password:
        flash("Thieu username hoac password.", "danger")
        return redirect(url_for("admin_users"))
    if database.get_user_by_username(username):
        flash(f"Username '{username}' da ton tai.", "danger")
        return redirect(url_for("admin_users"))
    try:
        database.create_user(username, password, role)
        flash(f"Da tao user '{username}'.", "success")
    except Exception as e:
        flash(f"Loi: {e}", "danger")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/edit", methods=["POST"])
@admin_required
def admin_edit_user(user_id):
    username = request.form.get("username", "").strip() or None
    password = request.form.get("password", "") or None
    role = request.form.get("role", "") or None
    try:
        database.update_user(user_id, username=username, password=password, role=role)
        flash("Da cap nhat user.", "success")
    except Exception as e:
        flash(f"Loi: {e}", "danger")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    if user_id == session["user_id"]:
        flash("Khong the tu xoa minh.", "danger")
        return redirect(url_for("admin_users"))
    database.delete_user(user_id)
    flash("Da xoa user.", "success")
    return redirect(url_for("admin_users"))


# ===== API CHO AGENT =====

@app.route("/api/ping")
def api_ping():
    return jsonify({"ok": True, "time": datetime.now().isoformat()})


@app.route("/api/jobs/poll")
@api_auth_required
def api_poll_job():
    """
    Agent goi de poll job. Phai mang header X-Auth-Token hop le.
    Tu dong ghi nho IP agent de proxy folder browse.
    """
    # Ghi nho IP agent (qua remote_addr) cho folder browser proxy
    try:
        _last_agent_ip["ip"] = request.remote_addr
    except Exception:
        pass

    job = database.get_next_job()
    if not job:
        return jsonify({"job": None})

    # Lay them thong tin user de agent thuc hien backup/restore.
    # Chi tra nhung truong agent thuc su can.
    user = database.get_user_by_id(job["user_id"])
    job["_user"] = {
        "id": user["id"],
        "username": user["username"],
        "token": user["token"],
        "encryption_key": user["encryption_key"]
    }
    if job.get("params"):
        try:
            job["params"] = json.loads(job["params"])
        except Exception:
            job["params"] = {}
    return jsonify({"job": job})


@app.route("/api/jobs/<int:job_id>/update", methods=["POST"])
@api_auth_required
def api_update_job(job_id):
    """Agent bao tien do va trang thai job"""
    data = request.json or {}
    updates = {}
    for k in ["status", "progress", "message"]:
        if k in data:
            updates[k] = data[k]
    if "completed" in data and data["completed"]:
        updates["completed_at"] = datetime.now().isoformat()
    if updates:
        database.update_job(job_id, **updates)
    return jsonify({"ok": True})


@app.route("/api/jobs/<int:job_id>/backup_done", methods=["POST"])
@api_auth_required
def api_backup_done(job_id):
    """Agent bao da backup xong - tao record trong bang backups"""
    data = request.json or {}
    job = database.get_job(job_id)
    if not job:
        return jsonify({"error": "job_not_found"}), 404

    backup_id = database.create_backup_record(
        user_id=job["user_id"],
        filename=data.get("filename"),
        paths=data.get("paths", []),
        backup_type=data.get("backup_type", "full")
    )
    database.update_backup(
        backup_id,
        size=data.get("size", 0),
        snapshot_summary=json.dumps(data.get("snapshot_summary", {})),
        status="completed"
    )
    database.update_job(job_id, backup_id=backup_id)
    return jsonify({"ok": True, "backup_id": backup_id})


# ===== STORAGE API (Agent upload/download file backup) =====

@app.route("/api/storage/upload", methods=["POST"])
def api_storage_upload():
    """Agent upload file backup vao folder cua user"""
    user = get_user_from_token()
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    if "file" not in request.files:
        return jsonify({"error": "no_file"}), 400

    f = request.files["file"]
    filename = secure_filename(request.form.get("filename") or f.filename)
    if not filename:
        return jsonify({"error": "bad_filename"}), 400

    user_dir = user_storage_dir(user["id"])
    save_path = os.path.join(user_dir, filename)

    # Save streaming
    f.save(save_path)
    size = os.path.getsize(save_path)

    print(f"[upload] user={user['username']} file={filename} size={size:,}")
    return jsonify({
        "ok": True,
        "path": f"user_{user['id']}/{filename}",
        "size": size
    })


@app.route("/api/storage/download")
def api_storage_download():
    """Agent download file backup"""
    user = get_user_from_token()
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    filename = secure_filename(request.args.get("filename", ""))
    if not filename:
        return jsonify({"error": "bad_filename"}), 400

    user_dir = user_storage_dir(user["id"])
    file_path = os.path.join(user_dir, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "not_found"}), 404

    return send_file(file_path, as_attachment=True, download_name=filename)


@app.route("/api/storage/list")
def api_storage_list():
    user = get_user_from_token()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    user_dir = user_storage_dir(user["id"])
    files = []
    for name in os.listdir(user_dir):
        path = os.path.join(user_dir, name)
        if os.path.isfile(path):
            files.append({
                "filename": name,
                "size": os.path.getsize(path),
                "modified": datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
            })
    return jsonify({"files": files})


@app.route("/api/storage/delete", methods=["POST"])
def api_storage_delete():
    user = get_user_from_token()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    data = request.json or {}
    filename = secure_filename(data.get("filename", ""))
    if not filename:
        return jsonify({"error": "bad_filename"}), 400
    user_dir = user_storage_dir(user["id"])
    path = os.path.join(user_dir, filename)
    if os.path.exists(path):
        os.remove(path)
        return jsonify({"ok": True})
    return jsonify({"error": "not_found"}), 404


# ===== FOLDER BROWSER PROXY (forward to agent) =====

# IP cua agent (Win 2012). De trong de tu phat hien theo IP cua agent gan day nhat.
AGENT_BROWSER_PORT = 5001
# Theo doi IP agent qua API polling (xem api_poll_job)
_last_agent_ip = {"ip": None}


def _get_agent_url():
    """Lay URL agent de proxy folder browse"""
    ip = _last_agent_ip.get("ip")
    if not ip:
        # Fallback: thu local
        return f"http://127.0.0.1:{AGENT_BROWSER_PORT}"
    return f"http://{ip}:{AGENT_BROWSER_PORT}"


@app.route("/api/folder-browser/quick")
@login_required
def api_browse_quick():
    """Lay quick picks tu agent (server proxy den agent)"""
    try:
        url = f"{_get_agent_url()}/folders/quick"
        r = _requests.get(url, timeout=10)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": f"Khong ket noi duoc den agent: {e}",
                        "agent_url": _get_agent_url()}), 502


@app.route("/api/folder-browser/list")
@login_required
def api_browse_list():
    """Liet ke thu muc tu agent (server proxy den agent)"""
    path = request.args.get("path", "")
    try:
        url = f"{_get_agent_url()}/folders/list"
        r = _requests.get(url, params={"path": path}, timeout=15)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": f"Khong ket noi duoc den agent: {e}",
                        "agent_url": _get_agent_url()}), 502


# ===== SCHEDULE ROUTES (Lap lich backup tu dong) =====

@app.route("/schedules")
@login_required
def schedules_page():
    """Trang quan ly lich backup"""
    user = current_user()
    if user["role"] == "admin":
        scheds = scheduler.list_schedules()
    else:
        scheds = scheduler.list_schedules(user["id"])
    return render_template("schedules.html", user=user, schedules=scheds)


@app.route("/schedules/add", methods=["POST"])
@login_required
def add_schedule():
    """Tao lich backup moi"""
    user = current_user()
    name = request.form.get("name", "").strip()
    schedule_type = request.form.get("schedule_type", "daily")
    interval_hours = int(request.form.get("interval_hours", 24) or 24)
    time_of_day = request.form.get("time_of_day", "02:00")
    day_of_week = int(request.form.get("day_of_week", 0) or 0)
    selected_path = request.form.get("path", "").strip()

    if not name:
        flash("Vui long nhap ten lich backup.", "danger")
        return redirect(url_for("schedules_page"))

    backup_paths = [selected_path] if selected_path else None
    sched_id = scheduler.create_schedule(
        user["id"], name, schedule_type, interval_hours,
        time_of_day, day_of_week, backup_paths
    )
    flash(f"Da tao lich backup '{name}' (#{sched_id}).", "success")
    return redirect(url_for("schedules_page"))


@app.route("/schedules/<int:sched_id>/toggle", methods=["POST"])
@login_required
def toggle_schedule_route(sched_id):
    """Bat/tat lich backup"""
    user = current_user()
    sched = scheduler.get_schedule(sched_id)
    if not sched or (sched["user_id"] != user["id"] and user["role"] != "admin"):
        flash("Lich khong ton tai.", "danger")
        return redirect(url_for("schedules_page"))
    new_state = scheduler.toggle_schedule(sched_id)
    status = "bat" if new_state else "tat"
    flash(f"Da {status} lich backup '{sched['name']}'.", "info")
    return redirect(url_for("schedules_page"))


@app.route("/schedules/<int:sched_id>/delete", methods=["POST"])
@login_required
def delete_schedule_route(sched_id):
    """Xoa lich backup"""
    user = current_user()
    sched = scheduler.get_schedule(sched_id)
    if not sched or (sched["user_id"] != user["id"] and user["role"] != "admin"):
        flash("Lich khong ton tai.", "danger")
        return redirect(url_for("schedules_page"))
    scheduler.delete_schedule(sched_id)
    flash(f"Da xoa lich backup '{sched['name']}'.", "success")
    return redirect(url_for("schedules_page"))


@app.route("/api/schedules")
@login_required
def api_schedules():
    """API lay danh sach lich (cho auto-refresh)"""
    user = current_user()
    if user["role"] == "admin":
        scheds = scheduler.list_schedules()
    else:
        scheds = scheduler.list_schedules(user["id"])
    return jsonify(scheds)


# ===== STARTUP =====

if __name__ == "__main__":
    print("="*60)
    print("  BACKUP SYSTEM - SERVER")
    print("  Chay tren Windows Server 2016 (vai tro storage)")
    print(f"  Lang nghe tai: http://{config.SERVER_HOST}:{config.SERVER_PORT}")
    print(f"  Storage path: {config.STORAGE_DIR}")
    print(f"  Database:     {config.DB_PATH}")
    print("="*60)
    print()
    print("  Tai khoan mac dinh:")
    print("    admin / admin123")
    print("    user1 / user123")
    print("="*60)

    database.init_db()

    # Khoi dong scheduler thread (lap lich backup tu dong)
    scheduler.start_scheduler()
    print("  [OK] Scheduler da khoi dong - tu dong chay backup theo lich")
    print("="*60)

    app.run(host=config.SERVER_HOST, port=config.SERVER_PORT, debug=False, threaded=True)
