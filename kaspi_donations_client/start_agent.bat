@echo off
title Kaspi Donations Agent
chcp 65001 >nul
cd /d "%~dp0"
echo [INFO] Запуск локального агента...
python agent.py
pause