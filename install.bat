@echo off
title BACKUP SYSTEM - Cai dat
echo ============================================================
echo  BACKUP SYSTEM - Cai dat thu vien Python
echo ============================================================
echo.

cd /d "%~dp0"

:: Kiem tra Python
python --version > nul 2>&1
if errorlevel 1 (
    echo [LOI] Python chua duoc cai dat!
    echo Hay cai Python 3.11 tai: https://www.python.org/downloads/windows/
    echo Nho tick "Add Python to PATH" khi cai.
    pause
    exit /b 1
)

python --version
echo.

:: Thu cai online truoc
echo [1/2] Thu cai truc tiep tu internet...
pip install flask requests cryptography --quiet 2>nul
if not errorlevel 1 (
    echo [OK] Cai dat thanh cong tu internet!
    goto :done
)

:: Neu co folder wheels (offline) thi cai tu do
if exist "wheels\" (
    echo [2/2] Cai tu folder wheels (offline)...
    pip install --no-index --find-links=wheels flask requests cryptography
    if not errorlevel 1 (
        echo [OK] Cai dat thanh cong tu offline!
        goto :done
    )
    echo [LOI] Offline cai that bai.
    goto :fail
)

:fail
echo.
echo ============================================================
echo  [LOI] Khong cai duoc. Co 2 cach sua:
echo.
echo  CACH 1 (De nhat): Chuyen Network Adapter sang NAT
echo  1. Tat VM
echo  2. VMware: Edit VM Settings ^> Network Adapter ^> NAT
echo  3. Bat VM lai, chay install.bat
echo  4. Xong thi chuyen lai Host-only
echo.
echo  CACH 2 (Offline): Chay download_wheels.bat tren may HOST
echo  sau do copy folder "wheels" vao may ao roi chay lai install.bat
echo ============================================================
pause
exit /b 1

:done
echo.
echo [OK] Tat ca thu vien da duoc cai dat!
echo.
echo  Ban co the chay:
echo    start_server.bat  (tren Win Server 2016)
echo    start_agent.bat   (tren Win Server 2012)
echo ============================================================
pause
