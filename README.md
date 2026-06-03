# Giải pháp Backup toàn diện và hiệu quả cho doanh nghiệp

> Đồ án cơ sở — Chuyên ngành Mạng máy tính — Trường Đại học Công nghệ TP.HCM (HUTECH)
> SVTH: **Đỗ Hồng Anh Duy** — MSSV: 2380603083 — Lớp: 23DTHC3 — GVHD: Nguyễn Văn Cẩn

Hệ thống sao lưu (backup) và khôi phục (restore) theo mô hình **Client–Server** chạy trên mạng LAN nội bộ, dành cho doanh nghiệp nhỏ. Điểm khác biệt so với các công cụ thông thường: ngoài file người dùng, hệ thống còn sao lưu và phục hồi **toàn bộ cấu hình mạng và hệ thống của Windows Server** — phần thường bị bỏ qua nhưng lại mất nhiều thời gian nhất khi dựng lại máy chủ.

---

## Tính năng chính

- **Sao lưu toàn diện**: file người dùng + 6 thành phần cấu hình mạng + SQL Server + Windows Registry.
  - 6 thành phần mạng: card mạng IPv4/IPv6, Windows Firewall (3 profile), Routing Table & Persistent Route, file Hosts, SMB Network Shares, Port Proxy.
- **Mã hóa AES-256 (CBC)** dạng streaming — mỗi user một khóa riêng (sinh từ Fernet rồi suy ra qua SHA-256), IV ngẫu nhiên cho mỗi lần mã hóa.
- **Snapshot SHA-256** — băm từng file để phát hiện thay đổi (thiếu / dư / sửa / giữ nguyên), giúp restore an toàn theo delta.
- **Nén tar.gz** mức 6, cân bằng giữa tốc độ và dung lượng.
- **Xác thực bằng token** qua header `X-Auth-Token` cho REST API; mỗi user chỉ truy cập dữ liệu của mình.
- **Lập lịch tự động** (hourly / daily / weekly) bằng luồng chạy nền.
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

- **Server (Win Server 2016)**: web UI, REST API, cơ sở dữ liệu SQLite, bộ lập lịch, kho lưu file backup theo từng user.
- **Agent (Win Server 2012 R2)**: cứ 3 giây gọi `/api/jobs/poll` hỏi job mới, rồi thực hiện backup/restore và báo tiến độ về server.

---

## Công nghệ sử dụng

| Thành phần | Phiên bản |
|---|---|
| Python | 3.11 |
| Flask | 3.0 |
| Werkzeug | 3.0 |
| Requests | 2.31 |
| cryptography | 42.0 |
| CSDL | SQLite (tích hợp sẵn trong Python) |
| Giao diện | Bootstrap 5 |

---

## Cài đặt

Yêu cầu: Windows Server (hoặc Windows) có **Python 3.11**, chạy bằng quyền **Administrator**.

```bash
# Cài thư viện
pip install -r requirements.txt
```

Hoặc cài offline bằng wheel: chạy `download_wheels.bat` (tải sẵn) rồi `install.bat`.

---

## Cách chạy

### 1. Trên máy Server (Windows Server 2016 — 192.168.10.1)

```bash
cd server
python server.py
```

Mở trình duyệt: `http://192.168.10.1:5000`

Tài khoản mặc định:

| Username | Password | Vai trò |
|---|---|---|
| `admin` | `admin123` | Admin |
| `user1` | `user123` | User |

Vào trang **Admin → Users**, copy **Token** của user dùng cho agent.

### 2. Trên máy Agent (Windows Server 2012 R2 — 192.168.10.2)

Mở `agent/agent_config.txt`, dán token vào dòng `AGENT_TOKEN=`:

```
SERVER_URL=http://192.168.10.1:5000
AGENT_TOKEN=<token-cua-user>
```

Rồi chạy (bằng quyền Administrator):

```bash
cd agent
python agent.py
```

### 3. Sao lưu / khôi phục

Trên web: bấm **"Backup toàn bộ"** (hoặc dùng *Browse Folder* chọn thư mục) → agent tự nhận job và thực hiện. Muốn khôi phục thì bấm **Restore** ở dòng backup tương ứng trong lịch sử.

---

## Kiểm thử restore

Thư mục [`test-scripts/`](test-scripts/) chứa 9 cặp script (`doi_*` / `check_*`) để kiểm tra khôi phục từng thành phần mạng. Quy trình:

```
check_* (xem trạng thái gốc)  →  Backup trên web  →  doi_* (đổi trạng thái)
   →  Restore trên web  →  check_* (xác nhận đã về trạng thái gốc)
```

Chi tiết xem [`test-scripts/README_TEST.txt`](test-scripts/README_TEST.txt). Các file `doi_*` cần chạy bằng quyền Administrator.

---

## Cấu trúc thư mục

```
backup-system/
├── server/                 # Chạy trên Windows Server 2016
│   ├── server.py           # Web UI + REST API
│   ├── scheduler.py        # Lập lịch backup tự động
│   └── templates/          # login, dashboard, admin_users, schedules
├── agent/                  # Chạy trên Windows Server 2012 R2
│   ├── agent.py            # Polling job + điều phối
│   ├── backup_logic.py     # Đóng gói, nén, mã hóa, upload
│   ├── restore_logic.py    # Tải về, giải mã, so sánh delta, khôi phục
│   ├── system_state.py     # Capture/restore trạng thái hệ thống
│   ├── network_advanced.py # Routing, hosts, SMB share, port proxy, firewall
│   ├── sql_registry.py     # SQL Server + Windows Registry
│   ├── folder_browser.py   # Duyệt cây thư mục cho web UI
│   ├── agent_config.txt
│   └── sample_data/        # Dữ liệu mẫu để demo
├── shared/                 # Dùng chung
│   ├── config.py           # Cấu hình
│   ├── database.py         # SQLite: users, backups, jobs, schedules
│   ├── encryption_utils.py # AES-256 CBC
│   └── snapshot.py         # Snapshot SHA-256
├── test-scripts/           # Script test restore (doi_*/check_*)
├── requirements.txt
├── install.bat
├── download_wheels.bat
└── README.md
```

---

## Hạn chế & hướng phát triển

- Hiện chạy trong LAN, chưa hỗ trợ HTTPS và sao lưu offsite/đám mây.
- Mỗi lần sao lưu toàn bộ (full) — chưa làm incremental thật sự.
- Agent xử lý tuần tự một job tại một thời điểm.

Hướng phát triển: thêm HTTPS, sao lưu tăng dần + deduplication, hỗ trợ nhiều agent song song, lưu trữ lên đám mây theo quy tắc 3-2-1.

---

*Đồ án phục vụ mục đích học tập. Triển khai thực tế cần bổ sung HTTPS và sao lưu chính cơ sở dữ liệu chứa khóa mã hóa.*
