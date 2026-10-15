@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "REPO_URL=https://github.com/stoatech19-netizen/suno_prompter.git"
set "INSTALL_DIR=suno_prompter"

echo ============================================
echo  Suno Prompt Generator - Install
echo ============================================
echo.
echo This will download the app from GitHub into a
echo "%INSTALL_DIR%" folder next to this script, then run its setup.
echo An internet connection is required.
echo.

if exist "%INSTALL_DIR%\.git" (
    echo [INFO] "%INSTALL_DIR%" already exists and looks installed.
    echo To update it, just double-click its own run.bat instead -
    echo it checks for updates automatically every time it starts.
    pause
    exit /b 0
)

REM --- 1. Make sure git is available ---
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Git not found. Downloading Git for Windows...
    set "GIT_INSTALLER=%TEMP%\git-for-windows-installer.exe"
    powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $url = ((Invoke-RestMethod -Uri 'https://api.github.com/repos/git-for-windows/git/releases/latest').assets | Where-Object { $_.name -like '*-64-bit.exe' } | Select-Object -First 1).browser_download_url; Invoke-WebRequest -Uri $url -OutFile '!GIT_INSTALLER!' } catch { Write-Host ('[DETAIL] ' + $_.Exception.Message); exit 1 }"

    if not exist "!GIT_INSTALLER!" (
        echo.
        echo [ERROR] Could not download Git ^(see [DETAIL] above for the reason^).
        echo Please install it manually from https://git-scm.com/download/win
        echo and re-run this script.
        pause
        exit /b 1
    )

    echo [INFO] Installing Git for the current user, no admin rights required...
    "!GIT_INSTALLER!" /VERYSILENT /NORESTART /NOCANCEL /SP- /CURRENTUSER
    del /f /q "!GIT_INSTALLER!" >nul 2>nul

    REM The installer updates the registry, not this already-running script's
    REM PATH, so pull the user PATH back in before checking for git again.
    for /f "usebackq tokens=2,*" %%A in (`reg query "HKCU\Environment" /v Path 2^>nul`) do set "PATH=%%B;%PATH%"

    where git >nul 2>nul
    if !errorlevel! neq 0 (
        echo.
        echo [ERROR] Git installation did not finish as expected.
        echo Close this window, open a new one, and re-run this script so it
        echo picks up the newly installed git.
        pause
        exit /b 1
    )
    echo [OK] Git installed.
    > ".git_installed_by_bootstrap.txt" echo GIT_INSTALLED=1
)

echo.
echo [INFO] Cloning the app from GitHub...
echo.
git clone "%REPO_URL%" "%INSTALL_DIR%"
if not exist "%INSTALL_DIR%\setup.bat" (
    echo.
    echo [ERROR] Clone failed, or finished without the expected files.
    echo Check the network connection above and try again.
    pause
    exit /b 1
)

if exist ".git_installed_by_bootstrap.txt" (
    move /y ".git_installed_by_bootstrap.txt" "%INSTALL_DIR%\.git_installed_by_bootstrap.txt" >nul
)

echo.
echo [OK] Downloaded into "%INSTALL_DIR%". Running setup...
echo.
pushd "%INSTALL_DIR%"
call setup.bat
popd
