@echo off
title CHECK - IPv4
set ADAPTER=Ethernet0
echo ===== Cau hinh IPv4 hien tai cua "%ADAPTER%" =====
netsh interface ipv4 show config name="%ADAPTER%"
echo.
echo --- ipconfig (tom tat) ---
ipconfig
pause
