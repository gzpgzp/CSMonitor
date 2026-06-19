@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   csMonitor 一键启动脚本
echo ========================================
echo.

:: ---- 第1步：启动 NapCat ----
echo [1/2] 正在启动 NapCat 机器人...
cd /d "%~dp0robot\NapCat.Shell"
start "NapCat" cmd /c "run.bat 2092836515"

:: ---- 第2步：等待 NapCat 就绪（检测端口3000可连通） ----
echo [2/2] 等待 NapCat 启动完成...
set READY=0
for /L %%i in (1,1,60) do (
    if !READY!==0 (
        powershell -Command "try { $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',3000); $c.Close(); write-host 'OK' } catch { write-host 'FAIL' }" >"%TEMP%\napcat_check.tmp" 2>&1
        findstr /C:"OK" "%TEMP%\napcat_check.tmp" >nul 2>&1
        if !errorlevel!==0 (
            set READY=1
            echo NapCat 已就绪！
        ) else (
            echo   等待中... [%%i/60]
            timeout /t 3 /nobreak >nul
        )
    )
)

if !READY!==0 (
    echo [错误] NapCat 在 3 分钟内未启动，请检查 robot\NapCat.Shell
    pause
    exit /b 1
)

:: ---- 第3步：启动 csMonitor ----
echo.
echo 正在启动 csMonitor...
cd /d "%~dp0"
:loop
call run.bat
echo 程序崩了，5秒后重启...
timeout /t 5
goto loop
