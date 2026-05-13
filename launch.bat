@echo off
cd /d "%~dp0"
echo ========================================
echo   NAS 照片回忆
echo ========================================
echo.

REM 禁止生成 .pyc 缓存（避免旧字节码问题）
set PYTHONDONTWRITEBYTECODE=1

REM 启动 Everything 服务（如果存在）
if exist "everything\Everything64.exe" (
    set EVERYTHING_EXE=everything\Everything64.exe
) else if exist "everything\Everything.exe" (
    set EVERYTHING_EXE=everything\Everything.exe
)

if defined EVERYTHING_EXE (
    tasklist /FI "IMAGENAME eq Everything*.exe" 2>NUL | find /I "Everything" >NUL
    if errorlevel 1 (
        echo 正在启动 Everything 搜索服务...
        start "" /MIN "%EVERYTHING_EXE%" -startup
        timeout /t 3 /nobreak >NUL
        echo Everything 已启动
    ) else (
        echo Everything 已在运行
    )
)

REM Test mode: skip Y: drive scan, use existing DB
REM set PHOTO_TEST_MODE=1
REM python main.py ui

REM Full mode
python -B main.py ui

pause
