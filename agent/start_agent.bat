@echo off
title BACKUP AGENT (Win 2012)
echo ============================================================
echo  BACKUP SYSTEM - AGENT (chay tren Windows Server 2012)
echo ============================================================
echo.
echo Truoc khi chay, hay sua file agent_config.txt:
echo   SERVER_URL=http://IP_CUA_WIN_2016:5000
echo.
echo Hoac dat bien moi truong:
echo   set BACKUP_SERVER_URL=http://192.168.10.1:5000
echo.
echo De dung agent, dong cua so nay hoac nhan Ctrl+C
echo ============================================================
echo.

cd /d "%~dp0"
python agent.py
pause
