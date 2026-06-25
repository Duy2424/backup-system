@echo off
title DOI ALL - Doi trang thai tat ca thanh phan (CAN ADMINISTRATOR)

:: ===== Tu dong xin quyen Administrator (UAC) neu chua co =====
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Yeu cau quyen Administrator - dang xin nang quyen...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: >>> Sua ten card neu khac "Ethernet0" (xem bang: ipconfig) <<<
set ADAPTER=Ethernet0
set HOSTS=C:\Windows\System32\drivers\etc\hosts

echo ############################################################
echo #  DOI ALL  -  Doi 8 thanh phan sang gia tri KHAC (de test restore)
echo #  Card mang: %ADAPTER%
echo #  CANH BAO: buoc [7]/[8] doi IPv4/IPv6 co the ROT RDP.
echo #            Nen chay tren CONSOLE VM (VMware), khong qua RDP.
echo #            (2 buoc nay de o CUOI nen 6 buoc kia van chay xong.)
echo ############################################################
echo.

echo ============================================================
echo [1/8] FIREWALL  (all OFF, roi Domain=OFF / Private=ON / Public=OFF)
echo ============================================================
netsh advfirewall set allprofiles state off
netsh advfirewall set domainprofile state off
netsh advfirewall set privateprofile state on
netsh advfirewall set publicprofile state off
netsh advfirewall show allprofiles state
echo.

echo ============================================================
echo [2/8] HOSTS  -^> them dong  192.168.10.123 doi-test.local
echo ============================================================
echo 192.168.10.123 doi-test.local>> "%HOSTS%"
type "%HOSTS%"
echo.

echo ============================================================
echo [3/8] SMB SHARE  -^> tao "DoiTestShare" = C:\DoiTestShare
echo ============================================================
if not exist C:\DoiTestShare mkdir C:\DoiTestShare
echo noi dung test> C:\DoiTestShare\file1.txt
net share DoiTestShare=C:\DoiTestShare /remark:"Doi test share"
net share
echo.

echo ============================================================
echo [4/8] PERSISTENT ROUTE  -^> them 10.123.0.0/16 qua 192.168.10.1
echo ============================================================
route add 10.123.0.0 mask 255.255.0.0 192.168.10.1 metric 1 -p
route print -4
echo.

echo ============================================================
echo [5/8] PORT PROXY  -^> them 0.0.0.0:9090 chuyen den 127.0.0.1:8080
echo ============================================================
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=9090 connectaddress=127.0.0.1 connectport=8080
netsh interface portproxy show all
echo.

echo ============================================================
echo [6/8] WINDOWS DEFENDER  -^> TAT real-time (DisableRealtimeMonitoring = True)
echo ============================================================
echo (Neu Tamper Protection bat, Windows se chan lenh nay - vao Windows Security tat truoc.)
powershell -NoProfile -Command "Set-MpPreference -DisableRealtimeMonitoring $true"
powershell -NoProfile -Command "Get-MpPreference | Select-Object DisableRealtimeMonitoring"
echo.

echo ============================================================
echo [7/8] CARD MANG IPv4  -^> 192.168.10.50 / 255.255.255.0 / gw 192.168.10.1 / DNS 1.1.1.1
echo        (co the rot RDP - dang chay...)
echo ============================================================
netsh interface ipv4 set address name="%ADAPTER%" static 192.168.10.50 255.255.255.0 192.168.10.1
netsh interface ipv4 set dns name="%ADAPTER%" static 1.1.1.1
netsh interface ipv4 show config name="%ADAPTER%"
echo.

echo ============================================================
echo [8/8] CARD MANG IPv6  -^> them 2001:db8::99/64 + DNS 2001:4860:4860::8844
echo ============================================================
netsh interface ipv6 add address "%ADAPTER%" 2001:db8::99/64
netsh interface ipv6 set dnsservers name="%ADAPTER%" static 2001:4860:4860::8844 primary
netsh interface ipv6 show address "%ADAPTER%"
echo.

echo ############################################################
echo #  XONG - da doi 8 thanh phan.
echo #  -^> Len WEB UI bam "Restore", roi chay check_all.bat
echo #     de xac nhan tat ca da ve trang thai goc.
echo ############################################################
pause
