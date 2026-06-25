# Giải pháp Backup toàn diện và hiệu quả cho doanh nghiệp

> Đồ án cơ sở — Chuyên ngành Mạng máy tính — Trường Đại học Công nghệ TP.HCM (HUTECH)
> SVTH: **Đỗ Hồng Anh Duy** — MSSV: 2380603083 — Lớp: 23DTHC3 — GVHD: Nguyễn Văn Cẩn

Hệ thống sao lưu (backup) và khôi phục (restore) theo mô hình **Client–Server** chạy trên mạng LAN nội bộ, dành cho doanh nghiệp nhỏ. Điểm khác biệt so với các công cụ thông thường: ngoài file người dùng, hệ thống còn sao lưu và phục hồi **toàn bộ cấu hình mạng và hệ thống của Windows Server** — phần thường bị bỏ qua nhưng lại mất nhiều thời gian nhất khi dựng lại máy chủ.

> **Gói này gồm đầy đủ cả hai phía:** `server/` (Storage Server) và `agent/` (máy client), cùng `shared/` dùng chung và bộ script test. Triển khai thật cần 2 máy (xem [Cách chạy](#cách-chạy)).

---

## Tính năng chính

- **Sao lưu toàn diện**: file người dùng + 6 thành phần cấu hình mạng + SQL Server + Windows Registry.
  - 6 thành phần mạng: card mạng IPv4/IPv6, Windows Firewall (3 profile), Routing Table & Persistent Route, file Hosts, SMB Network Shares, Port Proxy.
- **Mã hóa AES-256 (CBC)** dạng streaming — mỗi user một khóa riêng (sinh từ Fernet rồi suy ra qua SHA-256), IV ngẫu nhiên cho mỗi lần mã hóa.
- **Snapshot SHA-256** — băm từng file để phát hiện thay đổi (thiếu / dư / sửa / giữ nguyên), giúp restore an toàn theo delta.
- **Nén tar.gz** mức 6, cân bằng giữa tốc độ và dung lượng.
- **Xác thực bằng token** qua header `X-Auth-Token` cho REST API; mỗi user chỉ truy cập dữ liệu của mình.
- **Lập lịch tự động** (hourly / daily / weekly) bằng luồng chạy nền (`server/scheduler.py`): đến hạn sẽ tự tạo job backup cho agent.
- **Giao diện web** (Flask + Bootstrap 5): dashboard, quản trị user, lập lịch, trình duyệt thư mục (folder picker), progress bar thời gian thực.

---

## Kiến trúc

```
        ┌─────────────────────────────┐         HTTP / REST          ┌──────────────────────────────┐
        │  STORAGE SERVER             │   Polling 3s + X-Auth-Token   │  AGENT (CLIENT)              │
        │  Windows Server 2016        │ <───────────────────────────  │  Windows Server 2012 R2     │
        │  192.168.10.1 : 5000        │                               │  192.168.10.2 : 5001        │
        │  Flask Web + REST API       │                               │  Backup / Restore           │
        │  SQLite + Scheduler         │  ──────────────────────────>  │  Folder Browser             │
        └─────────────────────────────┘     upload / download .bkup   └──────────────────────────────┘
                     LAN VMware Host-only — dải 192.168.10.0/24
```

- **Server (Win Server 2016)**: web UI, REST API, CSDL SQLite, bộ lập lịch, kho lưu file backup theo từng user.
- **Agent (Win Server 2012 R2)**: cứ 3 giây gọi `/api/jobs/poll` hỏi job mới, rồi thực hiện backup/restore và báo tiến độ; chạy thêm Folder Browser (cổng 5001) phục vụ folder picker trên web.

---

## Công nghệ sử dụng

| Thành phần | Phiên bản |
|---|---|
| Python | 3.11 |
| Flask | 3.0.0 |
| Werkzeug | 3.0.1 |
| Requests | 2.31.0 |
| cryptography | 42.0.5 |
| CSDL | SQLite (tích hợp sẵn trong Python) |
| Giao diện | Bootstrap 5 (CDN) |

(Phiên bản pin đúng theo `requirements.txt`.)

---

## Cài đặt

Yêu cầu: Windows Server (hoặc Windows) có **Python 3.11** trên **cả hai máy**, chạy bằng quyền **Administrator**.

Cách nhanh nhất — chạy `install.bat` (tự thử cài online, nếu không có mạng thì chuyển sang cài offline từ thư mục `wheels`). Hoặc cài thủ công:

```bash
pip install -r requirements.txt
```

> **Môi trường LAN Host-only không có Internet:** ở máy có mạng chạy `download_wheels.bat` để tải sẵn các wheel vào thư mục `wheels/`, copy sang máy đích rồi chạy `install.bat` (nó tự cài offline bằng `pip install --no-index --find-links wheels`).
>
> **Giao diện web nạp Bootstrap 5 qua CDN.** Nếu máy server không ra được Internet, tải `bootstrap.min.css` + `bootstrap.bundle.min.js` + bộ `bootstrap-icons` về `server/templates/` (hoặc `static/`) và sửa lại đường link trong `server/templates/base.html`.

---

## Cách chạy

### 1. Máy Server (Windows Server 2016 — 192.168.10.1)

Chạy `server/start_server.bat`, hoặc:

```bash
cd server
python server.py
```

Khi khởi động, server tự tạo CSDL (4 bảng: `users`, `backups`, `jobs`, `schedules`) và bật luồng scheduler. Mở trình duyệt: `http://192.168.10.1:5000`

Tài khoản mặc định:

| Username | Password | Vai trò |
|---|---|---|
| `admin` | `admin123` | Admin |
| `user1` | `user123` | User |

Vào trang **Quản trị user**, copy **Token** của user để dùng cho agent.

### 2. Máy Agent (Windows Server 2012 R2 — 192.168.10.2)

Mở `agent/agent_config.txt`, điền token vào dòng `AGENT_TOKEN=`:

```
SERVER_URL=http://192.168.10.1:5000
AGENT_TOKEN=<token-cua-user>
```

Rồi chạy `agent/start_agent.bat`, hoặc:

```bash
cd agent
python agent.py
```

Agent sẽ polling server mỗi 3 giây và mở Folder Browser ở cổng 5001.

### 3. Sao lưu / khôi phục

Trên web: bấm **"Backup toàn bộ"** (hoặc dùng *Browse Folder* chọn thư mục) → agent tự nhận job và thực hiện. Muốn khôi phục thì bấm **Restore** ở dòng backup tương ứng. Tab **Lịch backup** cho phép tạo lịch hourly/daily/weekly để scheduler tự chạy.

---

## Các module agent (máy client)

`agent/` gồm: polling job + điều phối (`agent.py`); đóng gói/nén/mã hóa/upload (`backup_logic.py`); tải về/giải mã/so delta/khôi phục (`restore_logic.py`); capture/restore trạng thái hệ thống (`system_state.py`, `network_advanced.py`); SQL Server + Registry (`sql_registry.py`); folder browser cổng 5001 (`folder_browser.py`); và giao tiếp lưu trữ với server (`remote_storage.py`). Logic mã hóa AES-256 CBC và snapshot SHA-256 nằm ở `shared/encryption_utils.py` và `shared/snapshot.py` (agent gọi lúc đóng gói/khôi phục). Thư mục `agent/sample_data/` chứa dữ liệu mẫu để test nhanh.

---

## Kiểm thử restore

Thư mục [`test-scripts/`](test-scripts/) chứa script kiểm tra khôi phục từng thành phần mạng.

- **Test nhanh (1 lần nhấn):** `check_all.bat` xem trạng thái cả 8 thành phần (chỉ hiển thị); `doi_all.bat` đổi cả 8 thành phần (tự xin quyền Administrator). Quy trình: `check_all` → bấm **Backup** trên web → `doi_all` → bấm **Restore** → `check_all` lại.
- **Test từng phần:** 9 cặp `check_*` / `doi_*`.

Quy trình tổng quát:

```
check_* (xem trạng thái gốc)  →  Backup trên web  →  doi_* (đổi trạng thái)
   →  Restore trên web  →  check_* (xác nhận đã về trạng thái gốc)
```

Chi tiết xem [`test-scripts/README_TEST.txt`](test-scripts/README_TEST.txt). Các file `doi_*` cần chạy bằng quyền Administrator.

---

## Cấu trúc thư mục

```
backup-system/
├── server/                      # Storage Server (Win Server 2016)
│   ├── server.py                # Web UI + REST API cho agent
│   ├── scheduler.py             # Lập lịch backup tự động (luồng chạy nền)
│   ├── start_server.bat         # Chạy nhanh server
│   └── templates/               # Giao diện web (Jinja2 + Bootstrap 5)
│       ├── base.html            # Layout chung (navbar, flash, CSS)
│       ├── login.html           # Trang đăng nhập
│       ├── dashboard.html       # Dashboard: backup/restore, folder picker, progress
│       ├── admin_users.html     # Quản trị user (CRUD + token cho agent)
│       └── schedules.html       # Quản lý lịch backup
├── agent/                       # Agent (Win Server 2012 R2)
│   ├── agent.py                 # Polling job mỗi 3s + điều phối backup/restore
│   ├── backup_logic.py          # Snapshot → nén → mã hóa → upload
│   ├── restore_logic.py         # Download → giải mã → so delta → khôi phục
│   ├── system_state.py          # Capture/restore IPv4, IPv6, hosts...
│   ├── network_advanced.py      # Firewall (export/import .wfw), routing, port proxy
│   ├── sql_registry.py          # Backup SQL Server + Windows Registry
│   ├── folder_browser.py        # HTTP server cổng 5001 cho folder picker
│   ├── remote_storage.py        # Upload/download file .bkup với server
│   ├── start_agent.bat          # Chạy nhanh agent
│   ├── agent_config.txt         # SERVER_URL + AGENT_TOKEN
│   └── sample_data/             # Dữ liệu mẫu để test
├── shared/                      # Dùng chung server & agent
│   ├── config.py                # Cấu hình (đường dẫn, IP, exclude, đọc agent_config.txt)
│   ├── database.py              # SQLite: users / backups / jobs / schedules
│   ├── encryption_utils.py      # AES-256 CBC (mã hóa/giải mã file, streaming)
│   └── snapshot.py              # SHA-256 snapshot + so sánh delta
├── test-scripts/                # Script test restore từng thành phần mạng
│   ├── README_TEST.txt
│   ├── check_all.bat            # Xem trạng thái cả 8 thành phần - 1 lần nhấn
│   ├── doi_all.bat              # Đổi cả 8 thành phần - 1 lần nhấn (tự xin admin)
│   ├── check_1..9_*.bat         # Xem trạng thái từng phần
│   └── doi_1..9_*.bat           # Đổi trạng thái từng phần (quyền Administrator)
├── install.bat                  # Cài thư viện (thử online, fallback offline)
├── download_wheels.bat          # Tải sẵn wheel để cài offline
├── requirements.txt
├── resolve_conflicts.py         # Tiện ích gỡ merge conflict (giữ nhánh HEAD)
├── .gitignore
├── LICENSE
├── README.md
├── README_FIXES.txt             # Ghi chú sửa lỗi & đồng bộ với báo cáo
└── KHOI_PHUC_AGENT.txt          # Ghi chú khôi phục agent (có thể xóa sau khi đã ổn)
```

---

## Hạn chế & hướng phát triển

- Hiện chạy trong LAN, chưa hỗ trợ HTTPS và sao lưu offsite/đám mây.
- Mỗi lần sao lưu toàn bộ (full) — chưa làm incremental thật sự.
- Agent xử lý tuần tự một job tại một thời điểm.
- Folder Browser đang hiển thị toàn bộ ổ đĩa của agent — nên giới hạn theo whitelist.

Hướng phát triển: thêm HTTPS, sao lưu tăng dần + deduplication, hỗ trợ nhiều agent song song, lưu trữ lên đám mây theo quy tắc 3-2-1.

---

*Đồ án phục vụ mục đích học tập. Triển khai thực tế cần bổ sung HTTPS và sao lưu chính cơ sở dữ liệu chứa khóa mã hóa.*
