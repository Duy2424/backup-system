@echo off
title BACKUP SERVER (Win 2016)
echo ============================================================
echo  BACKUP SYSTEM - SERVER (chay tren Windows Server 2016)
echo ============================================================
echo.
echo Server se lang nghe tai: http://0.0.0.0:5000
echo.
echo Tai khoan mac dinh:
echo   admin / admin123
echo   user1 / user123
echo.
echo De dung server, dong cua so nay hoac nhan Ctrl+C
echo ============================================================
echo.

cd /d "%~dp0"
python server.py
pause
