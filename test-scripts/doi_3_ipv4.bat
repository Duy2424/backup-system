@echo off
title DOI - IPv4
net session >nul 2>&1 || (echo [LOI] Chay bang quyen Administrator! & pause & exit /b 1)
:: >>> Sua ten card cho dung may neu khac "Ethernet0" (xem bang: ipconfig) <<<
set ADAPTER=Ethernet0
echo Dang doi IPv4 cua "%ADAPTER%" -^> 192.168.10.50 / 255.255.255.0 / gw 192.168.10.1 / DNS 1.1.1.1 ...
netsh interface ipv4 set address name="%ADAPTER%" static 192.168.10.50 255.255.255.0 192.168.10.1
netsh interface ipv4 set dns name="%ADAPTER%" static 1.1.1.1
echo.
echo Cau hinh IPv4 moi:
netsh interface ipv4 show config name="%ADAPTER%"
pause
