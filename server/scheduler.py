"""
Scheduler - lap lich backup tu dong (chay tren may Server - Win 2016)

Module nay cung cap:
  - CRUD cho bang `schedules` (da duoc tao trong database.init_db()):
      create_schedule / list_schedules / get_schedule / toggle_schedule / delete_schedule
  - start_scheduler(): khoi dong 1 luong chay nen, cu moi _CHECK_INTERVAL giay
    quet cac lich dang bat. Lich nao "den han" thi tu dong tao mot job backup
    (database.create_job) cho agent nhan va thuc hien.

Kieu lap lich ho tro: hourly / daily / weekly (khop mo ta trong bao cao - muc 3.1.7).
Cac ham CRUD lam viec truc tiep tren bang `schedules` qua database.get_db()
nen khong can sua database.py.
"""
import json
import time as _time
import threading
from datetime import datetime, timedelta

import database


# ===== TINH THOI DIEM CHAY KE TIEP =====

def _parse_hhmm(value):
    """Tach chuoi 'HH:MM' -> (gio, phut). Loi thi mac dinh 02:00."""
    try:
        hh, mm = str(value or "02:00").split(":")
        return int(hh), int(mm)
    except Exception:
        return 2, 0


def compute_next_run(schedule_type, interval_hours, time_of_day, day_of_week, frm=None):
    """
    Tinh thoi diem chay ke tiep (tu thoi diem `frm`, mac dinh la bay gio).
      - hourly : frm + interval_hours gio
      - daily  : lan toi cua time_of_day (hom nay neu chua qua, nguoc lai mai)
      - weekly : lan toi cua (day_of_week, time_of_day)  [Thu Hai = 0]
    Tra ve datetime.
    """
    now = frm or datetime.now()
    st = (schedule_type or "daily").lower()

    if st == "hourly":
        hrs = max(1, int(interval_hours or 1))
        return now + timedelta(hours=hrs)

    hh, mm = _parse_hhmm(time_of_day)
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)

    if st == "weekly":
        dow = int(day_of_week or 0) % 7          # Thu Hai = 0 (theo Python weekday())
        days_ahead = (dow - now.weekday()) % 7
        target = target + timedelta(days=days_ahead)
        if target <= now:
            target = target + timedelta(days=7)
        return target

    # daily (mac dinh)
    if target <= now:
        target = target + timedelta(days=1)
    return target


# ===== CRUD BANG schedules =====

def create_schedule(user_id, name, schedule_type, interval_hours,
                    time_of_day, day_of_week, backup_paths):
    """Tao lich backup moi. Tra ve id cua lich."""
    next_run = compute_next_run(
        schedule_type, interval_hours, time_of_day, day_of_week
    ).isoformat()
    with database.get_db() as conn:
        cur = conn.execute(
            """INSERT INTO schedules
               (user_id, name, schedule_type, interval_hours, time_of_day,
                day_of_week, backup_paths, enabled, next_run)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (user_id, name, schedule_type, interval_hours, time_of_day,
             day_of_week,
             json.dumps(backup_paths) if backup_paths is not None else None,
             next_run)
        )
        return cur.lastrowid


def list_schedules(user_id=None):
    """Liet ke lich. Khong truyen user_id -> lay tat ca (cho admin)."""
    with database.get_db() as conn:
        if user_id is None:
            rows = conn.execute(
                "SELECT * FROM schedules ORDER BY id DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM schedules WHERE user_id=? ORDER BY id DESC",
                (user_id,)
            ).fetchall()
        return [dict(r) for r in rows]


def get_schedule(sched_id):
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM schedules WHERE id=?", (sched_id,)
        ).fetchone()
        return dict(row) if row else None


def toggle_schedule(sched_id):
    """Bat/tat lich. Tra ve trang thai moi (True=bat, False=tat)."""
    with database.get_db() as conn:
        row = conn.execute(
            "SELECT enabled FROM schedules WHERE id=?", (sched_id,)
        ).fetchone()
        if not row:
            return None
        new_state = 0 if row["enabled"] else 1
        conn.execute(
            "UPDATE schedules SET enabled=? WHERE id=?", (new_state, sched_id)
        )
        return bool(new_state)


def delete_schedule(sched_id):
    with database.get_db() as conn:
        conn.execute("DELETE FROM schedules WHERE id=?", (sched_id,))


def _mark_run(sched, now):
    """Ghi nhan da chay: cap nhat last_run + tinh next_run moi."""
    next_run = compute_next_run(
        sched["schedule_type"], sched["interval_hours"],
        sched["time_of_day"], sched["day_of_week"], frm=now
    ).isoformat()
    with database.get_db() as conn:
        conn.execute(
            "UPDATE schedules SET last_run=?, next_run=? WHERE id=?",
            (now.isoformat(), next_run, sched["id"])
        )


# ===== LUONG CHAY NEN =====

_CHECK_INTERVAL = 30          # giay - chu ky quet lich
_scheduler_started = False


def _check_due():
    """Quet 1 luot: lich nao da den han thi tao job backup."""
    now = datetime.now()
    for s in list_schedules():
        if not s.get("enabled"):
            continue

        nr = s.get("next_run")
        if nr:
            try:
                due = now >= datetime.fromisoformat(nr)
            except Exception:
                due = True
        else:
            due = True
        if not due:
            continue

        # Lay danh sach path cua lich (None = dung mac dinh cua agent)
        paths = None
        if s.get("backup_paths"):
            try:
                paths = json.loads(s["backup_paths"])
            except Exception:
                paths = None

        database.create_job(
            s["user_id"], "backup",
            params={"paths": paths, "schedule_id": s["id"]}
        )
        _mark_run(s, now)
        print(f"[scheduler] Da tao job backup theo lich '{s['name']}' "
              f"(user_id={s['user_id']}).")


def _loop():
    while True:
        try:
            _check_due()
        except Exception as e:
            print(f"[scheduler] Loi khi quet lich: {e}")
        _time.sleep(_CHECK_INTERVAL)


def start_scheduler():
    """Khoi dong luong scheduler nen (idempotent - goi nhieu lan cung an toan)."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    t = threading.Thread(target=_loop, daemon=True, name="backup-scheduler")
    t.start()
