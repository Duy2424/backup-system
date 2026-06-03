@echo off
title DOI - Hosts file
net session >nul 2>&1 || (echo [LOI] Chay bang quyen Administrator! & pause & exit /b 1)
set HOSTS=C:\Windows\System32\drivers\etc\hosts
echo Dang doi hosts: them dong  192.168.10.123 doi-test.local ...
echo 192.168.10.123 doi-test.local>> "%HOSTS%"
echo.
echo Noi dung hosts hien tai:
type "%HOSTS%"
pause
