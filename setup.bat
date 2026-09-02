@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo  Suno Prompt Generator - Setup
echo ============================================
echo.
echo This will install Python (if needed) and all
echo required packages into a local .venv folder.
echo An internet connection is required.
echo.

set "PYEXE="

REM --- 1. Look for an existing Python install first ---
where python >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%P in ('where python') do (
        if not defined PYEXE set "PYEXE=%%P"
    )
)

if not defined PYEXE (
    py -3 --version >nul 2>nul
    if !errorlevel!==0 set "PYEXE=py -3"
)

if defined PYEXE (
    echo [OK] Found existing Python: !PYEXE!
) else (
    echo [INFO] Python not found. Downloading the official Python 3.12.7 installer...
    set "PY_INSTALLER=%TEMP%\python-3.12.7-amd64.exe"
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile '!PY_INSTALLER!' } catch { exit 1 }"

    if not exist "!PY_INSTALLER!" (
        echo.
        echo [ERROR] Could not download the Python installer.
        echo Please check the internet connection and try again, or install
        echo Python manually from https://www.python.org/downloads/ and re-run setup.bat.
        pause
        exit /b 1
    )

    echo [INFO] Installing Python for the current user, no admin rights required...
    "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0

    set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
    if not exist "!PYEXE!" (
        echo.
        echo [ERROR] Python installation did not finish as expected.
        echo Please install Python manually from https://www.python.org/downloads/
        echo ^(check "Add python.exe to PATH" during install^) and re-run setup.bat.
        pause
        exit /b 1
    )
    echo [OK] Python installed: !PYEXE!
)

echo.
echo [INFO] Creating virtual environment (.venv)...
"!PYEXE!" -m venv ".venv"
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Failed to create the virtual environment.
    pause
    exit /b 1
)

echo.
echo [INFO] Installing required packages (this can take a few minutes)...
".venv\Scripts\python.exe" -m pip install --no-cache-dir --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt
if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Failed to install dependencies. Check the internet connection and try again.
    pause
    exit /b 1
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [INFO] Created .env from .env.example.
)

echo.
echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo NEXT STEP: Open the .env file in this folder with Notepad
echo and enter your Gemini API key, for example:
echo.
echo     GEMINI_API_KEY=your-key-here
echo.
echo Don't have a key yet? Get a free one at:
echo     https://aistudio.google.com/apikey
echo.
echo Then double-click run.bat to start the app.
echo.
pause
