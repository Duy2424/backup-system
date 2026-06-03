@echo off
title CHECK - Firewall (3 profile)
echo ===== Trang thai Firewall hien tai (Domain/Private/Public) =====
netsh advfirewall show allprofiles state
pause
