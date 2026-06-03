@echo off
title DOI - IPv6
net session >nul 2>&1 || (echo [LOI] Chay bang quyen Administrator! & pause & exit /b 1)
set ADAPTER=Ethernet0
echo Dang doi IPv6: them dia chi 2001:db8::99/64 + DNS 2001:4860:4860::8844 ...
netsh interface ipv6 add address "%ADAPTER%" 2001:db8::99/64
netsh interface ipv6 set dnsservers name="%ADAPTER%" static 2001:4860:4860::8844 primary
echo.
echo Dia chi IPv6 moi:
netsh interface ipv6 show address "%ADAPTER%"
pause
