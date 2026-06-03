============================================================
  SCRIPT TEST RESTORE  -  Moi test 2 file (doi + check)
============================================================
Moi thanh phan co 2 file, nhan (double-click) la chay ngay:

  doi_*.bat    : DOI trang thai hien tai sang mot gia tri KHAC.
  check_*.bat  : XEM trang thai hien tai (chi hien, khong sua gi).

------------------------------------------------------------
CACH TEST 1 THANH PHAN (vd IPv4):
------------------------------------------------------------
  1. Nhan  check_3_ipv4.bat   -> xem IP hien tai (vd .2). Day la trang thai goc.
  2. Len WEB UI bam "BACKUP TOAN BO", doi backup xong.   (backup luu trang thai goc)
  3. Nhan  doi_3_ipv4.bat     -> IP doi sang 192.168.10.50.
  4. Nhan  check_3_ipv4.bat   -> xac nhan da doi (thay .50).
  5. Len WEB UI bam "Restore" tu ban backup vua tao, doi xong.
  6. Nhan  check_3_ipv4.bat   -> neu IP ve lai trang thai goc => RESTORE DUNG.

Tom lai: check (xem goc) -> backup -> doi -> restore -> check (xem da ve goc chua).

------------------------------------------------------------
DANH SACH FILE (9 cap):
------------------------------------------------------------
  Firewall 3 profile    doi_1_firewall_all.bat        check_1_firewall_all.bat
  Firewall tung profile doi_2_firewall_perprofile.bat check_2_firewall_perprofile.bat
  Card mang IPv4        doi_3_ipv4.bat                check_3_ipv4.bat
  Card mang IPv6        doi_4_ipv6.bat                check_4_ipv6.bat
  Hosts file           doi_5_hosts.bat               check_5_hosts.bat
  SMB share            doi_6_shares.bat              check_6_shares.bat
  Persistent route     doi_7_route.bat               check_7_route.bat
  Port proxy           doi_8_portproxy.bat           check_8_portproxy.bat
  Windows Defender     doi_9_defender.bat            check_9_defender.bat

------------------------------------------------------------
LUU Y:
------------------------------------------------------------
  - Cac file doi_*.bat can chay bang quyen ADMINISTRATOR
    (chuot phai -> Run as administrator). Neu nhan thuong se bao loi.
  - Chay tren may AGENT (Win Server 2012 R2).
  - Rieng doi_3 (IPv4) va doi_4 (IPv6): doi IP co the rot RDP -> chay
    tren MAN HINH VM (console VMware). IP moi van cung subnet voi
    server (.1) nen agent van len duoc server.
  - Mo file sua bien dau file neu can:
       set ADAPTER=Ethernet0   (ten card - xem bang lenh ipconfig)
  - doi_9 (Defender): neu Tamper Protection bat thi Windows chan lenh,
    vao Windows Security tat Tamper Protection truoc.

------------------------------------------------------------
MUON DEMO "TOAN BO" 1 LUOT:
------------------------------------------------------------
  check tat ca -> backup 1 lan -> chay LAN LUOT tat ca doi_*.bat
  -> restore 1 lan -> check lai tat ca. Khong can file rieng.
============================================================
