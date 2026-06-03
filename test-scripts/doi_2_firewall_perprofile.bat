@echo off
title DOI - Firewall tung profile
net session >nul 2>&1 || (echo [LOI] Chay bang quyen Administrator! & pause & exit /b 1)
echo Dang doi: Domain=OFF, Private=ON, Public=OFF ...
netsh advfirewall set domainprofile state off
netsh advfirewall set privateprofile state on
netsh advfirewall set publicprofile state off
echo.
echo Trang thai moi:
netsh advfirewall show allprofiles state
pause
