@echo off
title DOI - Port Proxy
net session >nul 2>&1 || (echo [LOI] Chay bang quyen Administrator! & pause & exit /b 1)
echo Dang doi: them port proxy  0.0.0.0:9090 -^> 127.0.0.1:8080 ...
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=9090 connectaddress=127.0.0.1 connectport=8080
echo.
echo Danh sach port proxy hien tai:
netsh interface portproxy show all
pause
