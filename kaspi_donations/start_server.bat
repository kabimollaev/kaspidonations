@echo off
title Kaspi Donations Server
color 0A

:: Эта команда гарантирует, что скрипт всегда запускается из своей папки
cd /d "%~dp0"

echo.
echo ===========================================
echo   Starting Kaspi Donations Server...
echo ===========================================
echo.

REM --- Проверка наличия Python ---
echo [INFO] Checking for Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b
)

REM --- Установка всех необходимых библиотек ---
echo [INFO] Installing all required libraries...
python -m pip install --upgrade flask flask-sock gtts

if %errorlevel% neq 0 (
    echo.
    echo [CRITICAL ERROR] Failed to install Python libraries.
    pause
    exit /b
)
echo [INFO] All libraries are installed.

echo [INFO] Launching server.py...
echo [INFO] This window will now stay open reliably.
echo.

cmd /k python server.py

