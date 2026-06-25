@echo off
title CHECK ALL - Xem trang thai tat ca thanh phan (chi hien, khong sua)
set ADAPTER=Ethernet0
set HOSTS=C:\Windows\System32\drivers\etc\hosts

echo ############################################################
echo #  CHECK ALL  -  Xem trang thai HIEN TAI (chi hien thi, khong sua gi)
echo #  Card mang dang dung: %ADAPTER%   (sua dong "set ADAPTER=" neu khac)
echo ############################################################
echo.

echo ============================================================
echo [1/8] FIREWALL  (3 profile: Domain / Private / Public)
echo ============================================================
netsh advfirewall show allprofiles state
echo.

echo ============================================================
echo [2/8] HOSTS FILE
echo ============================================================
type "%HOSTS%"
echo.

echo ============================================================
echo [3/8] SMB SHARE
echo ============================================================
net share
echo.

echo ============================================================
echo [4/8] ROUTING TABLE (IPv4)
echo ============================================================
route print -4
echo.

echo ============================================================
echo [5/8] PORT PROXY
echo ============================================================
netsh interface portproxy show all
echo.

echo ============================================================
echo [6/8] WINDOWS DEFENDER (real-time)
echo ============================================================
echo (DisableRealtimeMonitoring = True  -^> real-time DANG TAT)
powershell -NoProfile -Command "Get-MpPreference | Select-Object DisableRealtimeMonitoring, DisableBehaviorMonitoring"
echo.

echo ============================================================
echo [7/8] CARD MANG IPv4  -  "%ADAPTER%"
echo ============================================================
netsh interface ipv4 show config name="%ADAPTER%"
echo.
echo --- ipconfig (tom tat) ---
ipconfig
echo.

echo ============================================================
echo [8/8] CARD MANG IPv6  -  "%ADAPTER%"
echo ============================================================
netsh interface ipv6 show address "%ADAPTER%"
echo.

echo ############################################################
echo #  XONG - da xem xong 8 thanh phan.
echo ############################################################
pause
