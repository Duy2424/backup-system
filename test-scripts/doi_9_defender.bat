@echo off
title DOI - Windows Defender real-time
net session >nul 2>&1 || (echo [LOI] Chay bang quyen Administrator! & pause & exit /b 1)
:: Luu y: neu Tamper Protection bat, Windows se chan lenh nay.
set CUR=
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "(Get-MpPreference).DisableRealtimeMonitoring"`) do set CUR=%%i
echo Real-time hien tai: DisableRealtimeMonitoring = %CUR%
if /i "%CUR%"=="True" (
    echo Dang BAT lai real-time protection...
    powershell -NoProfile -Command "Set-MpPreference -DisableRealtimeMonitoring $false"
) else (
    echo Dang TAT real-time protection...
    powershell -NoProfile -Command "Set-MpPreference -DisableRealtimeMonitoring $true"
)
echo.
echo Trang thai moi:
powershell -NoProfile -Command "Get-MpPreference | Select-Object DisableRealtimeMonitoring"
pause
