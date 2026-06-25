@echo off
title Download packages cho offline install
echo ============================================================
echo  Chay script nay tren may HOST (co internet)
echo  de tai cac goi Python ve, sau do copy folder "wheels"
echo  vao may ao (Win 2012 va Win 2016) cung thu muc backup-system
echo ============================================================
echo.

cd /d "%~dp0"

:: Xoa wheels cu
if exist "wheels\" (
    echo Xoa wheels cu...
    rmdir /s /q wheels
)
mkdir wheels

echo Dang tai packages cho Windows (64-bit, Python 3.11)...
echo.

pip download flask requests cryptography ^
    --dest wheels ^
    --platform win_amd64 ^
    --python-version 311 ^
    --implementation cp ^
    --only-binary :all: 2>nul

:: Cuoi cung: tai bat ky version nao duoc
pip download flask requests cryptography --dest wheels

echo.
if exist "wheels\flask*" (
    echo [OK] Tai xong! Cac file trong thu muc "wheels":
    dir wheels /b
    echo.
    echo Buoc tiep theo:
    echo   1. Copy ca thu muc "wheels" nay vao may ao
    echo      (cung thu muc voi backup-system)
    echo   2. Chay lai install.bat tren may ao
) else (
    echo [LOI] Tai that bai. Hay kiem tra ket noi internet.
)
echo ============================================================
pause
