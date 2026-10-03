@echo off
chcp 65001 > nul
title Discord Sound Bot

echo ===================================================
echo              DISCORD SOUND BOT
echo     (Spotify, SoundCloud, Deezer Voice Player)
echo ===================================================
echo.

if not exist .env (
    echo [УВАГА] Файл .env не знайдено!
    echo Створюю файл .env зі зразка .env.example...
    copy .env.example .env > nul
    echo Будь ласка, відкрийте файл .env та вставте ваш DISCORD_TOKEN!
    echo.
    pause
    notepad .env
    exit /b
)

if not exist .venv (
    echo Створення віртуального середовища .venv...
    python -m venv .venv
    echo Встановлення залежностей...
    call .\.venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call .\.venv\Scripts\activate.bat
)

echo Запуск бота...
python main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Бот завершив роботу з кодом помилки %ERRORLEVEL%.
    pause
)
