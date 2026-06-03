@echo off
title DOI - Persistent Route
net session >nul 2>&1 || (echo [LOI] Chay bang quyen Administrator! & pause & exit /b 1)
echo Dang doi: them persistent route  10.123.0.0/16 -^> 192.168.10.1 ...
route add 10.123.0.0 mask 255.255.0.0 192.168.10.1 metric 1 -p
echo.
echo Bang dinh tuyen IPv4 hien tai:
route print -4
pause
