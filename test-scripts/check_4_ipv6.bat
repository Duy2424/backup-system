@echo off
title CHECK - IPv6
set ADAPTER=Ethernet0
echo ===== Dia chi IPv6 hien tai cua "%ADAPTER%" =====
netsh interface ipv6 show address "%ADAPTER%"
pause
