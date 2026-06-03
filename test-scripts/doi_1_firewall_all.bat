@echo off
title DOI - Firewall (3 profile)
net session >nul 2>&1 || (echo [LOI] Chay bang quyen Administrator! & pause & exit /b 1)
echo Dang doi: tat ca 3 profile firewall -^> OFF ...
netsh advfirewall set allprofiles state off
echo.
echo Trang thai moi:
netsh advfirewall show allprofiles state
pause
