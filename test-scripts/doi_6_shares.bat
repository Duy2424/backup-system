@echo off
title DOI - SMB Share
net session >nul 2>&1 || (echo [LOI] Chay bang quyen Administrator! & pause & exit /b 1)
echo Dang doi: tao share "DoiTestShare" -^> C:\DoiTestShare ...
if not exist C:\DoiTestShare mkdir C:\DoiTestShare
echo noi dung test> C:\DoiTestShare\file1.txt
net share DoiTestShare=C:\DoiTestShare /remark:"Doi test share"
echo.
echo Danh sach share hien tai:
net share
pause
