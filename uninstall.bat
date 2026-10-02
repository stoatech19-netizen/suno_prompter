@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo  Suno Prompt Generator - Uninstall
echo ============================================
echo.
echo This will remove, from THIS FOLDER only:
echo   - .venv  (the Python virtual environment and all installed packages)
echo   - any uploaded temp files left in uploads\
echo.
echo Your Gemini API key is stored in the browser (not in this folder), so
echo it isn't touched by this uninstall.
echo.

set /p "CONFIRM=Continue? (y/n): "
if /i not "!CONFIRM!"=="y" (
    echo Cancelled.
    pause
    exit /b 0
)

if exist ".venv" (
    echo [INFO] Removing .venv ...
    rmdir /s /q ".venv"
)

if exist "uploads" (
    for %%F in ("uploads\*") do (
        if /i not "%%~nxF"==".gitkeep" del /f /q "%%F" >nul 2>nul
    )
)

echo.
echo [OK] This folder has been cleaned back to its pre-setup state.
echo You can now delete the whole suno_prompter folder if you no longer need it.

if exist ".python_installed_by_setup.txt" (
    set "PYVER="
    for /f "usebackq tokens=1,* delims==" %%A in (".python_installed_by_setup.txt") do (
        if /i "%%A"=="PYTHON_VERSION" set "PYVER=%%B"
    )
    echo.
    echo ------------------------------------------------------------
    echo NOTE: setup.bat also installed Python !PYVER! on this PC,
    echo because no working Python was found here before.
    echo.
    set /p "REMOVEPY=Also uninstall that Python !PYVER! now? (y/n): "
    if /i "!REMOVEPY!"=="y" (
        echo [INFO] Downloading the Python !PYVER! installer to run its uninstaller...
        set "PY_UNINSTALLER=%TEMP%\python-!PYVER!-amd64-uninstall.exe"
        powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/!PYVER!/python-!PYVER!-amd64.exe' -OutFile '!PY_UNINSTALLER!' } catch { Write-Host ('[DETAIL] ' + $_.Exception.Message); exit 1 }"
        if exist "!PY_UNINSTALLER!" (
            echo [INFO] Uninstalling Python !PYVER! ...
            "!PY_UNINSTALLER!" /uninstall /quiet
            del /f /q "!PY_UNINSTALLER!" >nul 2>nul
            echo [OK] Python !PYVER! uninstalled.
        ) else (
            echo [ERROR] Could not download the uninstaller ^(see [DETAIL] above^).
            echo Remove it manually instead: Settings ^> Apps ^> search "Python !PYVER!" ^> Uninstall.
        )
    ) else (
        echo [INFO] Left Python !PYVER! installed. You can remove it later via
        echo Settings ^> Apps ^> search "Python !PYVER!" ^> Uninstall.
    )
    del /f /q ".python_installed_by_setup.txt" >nul 2>nul
)

echo.
echo Done.
pause
