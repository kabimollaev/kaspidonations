@echo off
title Kaspi Donations Agent
chcp 65001 >nul
cd /d "%~dp0"

echo [INFO] Запуск Kaspi Donations Agent (Python версия)...
echo [INFO] Дата: %date% %time%
echo.

REM Создаем лог файл
set LOG_FILE=agent_start.log
echo === Запуск Kaspi Agent === > "%LOG_FILE%"
echo Дата: %date% %time% >> "%LOG_FILE%"

REM Проверка установки Python
echo [INFO] Проверка Python...
echo Проверка Python... >> "%LOG_FILE%"
python --version >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
echo [ERROR] Python не установлен или не добавлен в PATH >> "%LOG_FILE%"
echo [ERROR] Python не установлен или не добавлен в PATH
echo Установите Python с официального сайта: https://python.org
echo Убедитесь, что отметили галочку "Add Python to PATH" при установке
pause
exit /b 1
)

echo [INFO] Python найден >> "%LOG_FILE%"
echo [INFO] Python найден

REM Проверка и установка зависимостей
echo [INFO] Проверка зависимостей...
echo Проверка зависимостей... >> "%LOG_FILE%"
pip install requests pystray pillow >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
echo [WARNING] Не удалось установить зависимости автоматически >> "%LOG_FILE%"
echo [WARNING] Не удалось установить зависимости автоматически
echo Попробуйте установить вручную: pip install requests pystray pillow
)

echo [INFO] Запуск агента...
echo Запуск агента... >> "%LOG_FILE%"
echo Команда: python agent.py >> "%LOG_FILE%"

REM Запуск Python скрипта
python agent.py >> "%LOG_FILE%" 2>&1

echo.
echo ========================================================
echo.
echo [INFO] Программа завершена. Нажмите любую клавишу для закрытия.
pause