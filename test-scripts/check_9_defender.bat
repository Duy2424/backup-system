@echo off
title CHECK - Windows Defender real-time
echo ===== Trang thai Windows Defender real-time hien tai =====
echo (DisableRealtimeMonitoring = True  -^> real-time DANG TAT)
powershell -NoProfile -Command "Get-MpPreference | Select-Object DisableRealtimeMonitoring, DisableBehaviorMonitoring"
pause
