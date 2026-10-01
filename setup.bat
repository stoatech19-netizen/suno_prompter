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
REM where.exe can also match the Windows "App Execution Alias" stub at
REM %LocalAppData%\Microsoft\WindowsApps\python.exe, which exists as a file
REM even when Python is NOT installed and just prints a Store prompt when
REM run. Actually running --version on each candidate filters that out.
where python >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%P in ('where python') do (
        if not defined PYEXE (
            "%%P" --version >nul 2>nul
            if !errorlevel!==0 set "PYEXE=%%P"
        )
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
    powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile '!PY_INSTALLER!' } catch { Write-Host ('[DETAIL] ' + $_.Exception.Message); exit 1 }"

    if not exist "!PY_INSTALLER!" (
        echo.
        echo [ERROR] Could not download the Python installer ^(see [DETAIL] above for the reason^).
        echo Please check the internet connection and try again, or install Python
        echo manually from https://www.python.org/downloads/ ^(check "Add python.exe
        echo to PATH" during install^) and re-run setup.bat.
        pause
        exit /b 1
    )

    echo [INFO] Installing Python for the current user, no admin rights required...
    "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0
    del /f /q "!PY_INSTALLER!" >nul 2>nul

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

    REM Record that THIS script installed Python, so uninstall.bat knows it
    REM is safe to offer removing it (and won't touch a pre-existing Python).
    > ".python_installed_by_setup.txt" echo PYTHON_VERSION=3.12.7
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
echo One last step: you need a Gemini API key ^(free^).
echo Don't have one yet? Get it here: https://aistudio.google.com/apikey
echo.
set "USER_KEY="
set /p "USER_KEY=Paste your Gemini API key here and press Enter (or just press Enter to skip): "

if not "!USER_KEY!"=="" (
    set "GEMINI_KEY_TO_WRITE=!USER_KEY!"
    powershell -NoProfile -Command "$k = $env:GEMINI_KEY_TO_WRITE; $lines = Get-Content '.env' -Encoding UTF8 | ForEach-Object { $_ -replace '^GEMINI_API_KEY=.*', ('GEMINI_API_KEY=' + $k) }; [System.IO.File]::WriteAllLines((Resolve-Path '.env'), $lines, (New-Object System.Text.UTF8Encoding($false)))"
    echo [OK] API key saved to .env.
) else (
    echo.
    echo [INFO] No key entered - skipped for now.
    echo Before running the app, open .env in this folder with Notepad and
    echo add a line like: GEMINI_API_KEY=your-key-here
    echo.
    pause
)

echo.
echo Setup finished. Double-click run.bat to start the app.
echo.
pause
