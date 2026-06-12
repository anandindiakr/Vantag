@echo off
title Vantag Edge Agent Setup
color 0A

echo ==============================================
echo   Vantag Edge Agent - Quick Test Setup
echo ==============================================
echo.

REM -- Step 1: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11 or 3.12 from:
    echo         https://www.python.org/downloads/
    echo         IMPORTANT: Tick "Add Python to PATH" during installation.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] %PYVER% detected

echo.
echo -- Step 2: Installing Python dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    echo Run manually: pip install -r requirements.txt
    pause
    exit /b 1
)
echo [OK] Dependencies installed

echo.
REM -- Step 3: Check config.json
if not exist config.json (
    if exist config.template.json (
        copy config.template.json config.json >nul
        echo [ACTION NEEDED] config.json created from template.
        echo.
        echo ============================================================
        echo  IMPORTANT: You must set your API key before continuing!
        echo.
        echo  1. Log in to https://retail-vantag.com
        echo  2. Go to: Install Edge Agent page
        echo  3. Copy your API Key
        echo  4. Paste it into config.json (api_key field)
        echo     File location: %~dp0config.json
        echo ============================================================
        echo.
        echo Opening config.json for editing...
        notepad config.json
        echo.
        echo Press any key AFTER saving your API key in config.json...
        pause
    ) else (
        echo [ERROR] No config.json found. Create it from config.template.json
        pause
        exit /b 1
    )
) else (
    echo [OK] config.json found
)

echo.
echo -- Step 4: Starting Vantag Edge Agent...
echo    Logs will appear below AND in: %%APPDATA%%\Vantag\agent.log
echo    A tray icon will appear in your taskbar (bottom-right).
echo    To stop: right-click the tray icon and choose "Quit"
echo.
python run_agent.py

echo.
echo Agent exited.
pause
