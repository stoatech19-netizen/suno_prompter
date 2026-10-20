@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Setup has not been run yet. Please double-click setup.bat first.
    pause
    exit /b 1
)

rem Just finding "git" on PATH isn't enough to safely run it: if it was
rem installed for the wrong CPU architecture (or the binary is otherwise
rem corrupt), Windows pops a blocking "wrong system type" dialog the
rem instant we try to launch it -- and since this window is hidden by
rem launch.vbs, that dialog looks exactly like the app silently failing
rem to start. Checked without ever running git.exe: read its PE header's
rem machine-type field directly and compare it to the OS's real
rem architecture (not the process's, in case this is 32-bit cmd under
rem WOW64/emulation).
set "GIT_OK=0"
for /f "delims=" %%G in ('powershell -NoProfile -Command "try { $g = (Get-Command git -ErrorAction Stop).Source; $b = [IO.File]::ReadAllBytes($g); $off = [BitConverter]::ToInt32($b, 0x3C); $mach = [BitConverter]::ToUInt16($b, $off + 4); $want = switch ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture) { 'X64' {0x8664} 'X86' {0x014c} 'Arm64' {0xAA64} 'Arm' {0x01c4} default {-1} }; if ($mach -eq $want) {'OK'} else {'MISMATCH'} } catch {'MISSING'}" 2^>nul') do set "GIT_OK=%%G"

rem The installer (Inno Setup exe) only bundles a .git snapshot and runs
rem setup.bat, which never checks for git -- unlike bootstrap.bat's clone
rem path, it assumes git already exists on the target PC. If it doesn't,
rem the update check below was silently skipped on every single launch
rem forever, permanently pinning the app to whatever snapshot happened to
rem be baked into that installer build. Install git here too (same
rem silent, per-user install bootstrap.bat already does) so this app can
rem self-update regardless of which path it was installed through.
if "!GIT_OK!"=="MISSING" (
    echo [INFO] git was not found - installing it now so this app can check for updates...
    set "GIT_INSTALLER=%TEMP%\git-for-windows-installer.exe"
    powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $url = ((Invoke-RestMethod -Uri 'https://api.github.com/repos/git-for-windows/git/releases/latest').assets | Where-Object { $_.name -like '*-64-bit.exe' } | Select-Object -First 1).browser_download_url; Invoke-WebRequest -Uri $url -OutFile '!GIT_INSTALLER!' } catch { exit 1 }" >nul 2>nul
    if exist "!GIT_INSTALLER!" (
        "!GIT_INSTALLER!" /VERYSILENT /NORESTART /NOCANCEL /SP- /CURRENTUSER
        del /f /q "!GIT_INSTALLER!" >nul 2>nul
        rem The installer updates the registry, not this already-running
        rem process's PATH, so pull the user PATH back in before re-checking.
        for /f "usebackq tokens=2,*" %%A in (`reg query "HKCU\Environment" /v Path 2^>nul`) do set "PATH=%%B;%PATH%"
        if not exist ".git_installed_by_bootstrap.txt" (
            > ".git_installed_by_bootstrap.txt" echo GIT_INSTALLED=1
        )
        for /f "delims=" %%G in ('powershell -NoProfile -Command "try { $g = (Get-Command git -ErrorAction Stop).Source; $b = [IO.File]::ReadAllBytes($g); $off = [BitConverter]::ToInt32($b, 0x3C); $mach = [BitConverter]::ToUInt16($b, $off + 4); $want = switch ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture) { 'X64' {0x8664} 'X86' {0x014c} 'Arm64' {0xAA64} 'Arm' {0x01c4} default {-1} }; if ($mach -eq $want) {'OK'} else {'MISMATCH'} } catch {'MISSING'}" 2^>nul') do set "GIT_OK=%%G"
        if "!GIT_OK!"=="OK" (
            echo [OK] git installed.
        ) else (
            echo [WARN] git install did not finish as expected - skipping the update check this time.
        )
    ) else (
        echo [WARN] Could not install git automatically ^(offline?^). Skipping the update check this time.
    )
    echo.
)

if "!GIT_OK!"=="OK" (
    if exist ".git" (
        echo Checking for updates...
        git fetch --quiet origin main >nul 2>nul
        if !errorlevel! equ 0 (
            for /f "delims=" %%H in ('git rev-parse HEAD') do set "LOCAL_HEAD=%%H"
            for /f "delims=" %%H in ('git rev-parse origin/main') do set "REMOTE_HEAD=%%H"
            if not "!LOCAL_HEAD!"=="!REMOTE_HEAD!" (
                echo [INFO] Update found. Applying...
                git diff --quiet HEAD origin/main -- requirements.txt
                set "REQS_CHANGED=!errorlevel!"
                git pull --ff-only origin main
                if !errorlevel! equ 0 (
                    if not "!REQS_CHANGED!"=="0" (
                        echo [INFO] Dependencies changed, reinstalling...
                        ".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt
                    )
                    echo [OK] Updated to the latest version.
                ) else (
                    echo [WARN] Could not apply the update automatically ^(local changes in this folder?^). Continuing with the current version.
                )
            )
        ) else (
            echo [WARN] Could not check for updates ^(offline?^). Continuing with the current version.
        )
        echo.
    )
) else (
    if "!GIT_OK!"=="MISMATCH" (
        echo [WARN] The 'git' on this PC is built for a different CPU architecture and can't run here - skipping the update check.
    ) else (
        echo [WARN] 'git' was not found - skipping the update check.
    )
    echo Continuing with the current version.
    echo.
)

rem A previous instance can be left listening on 5001 if it didn't shut
rem down cleanly (crash, older version without the auto-stop heartbeat,
rem etc). If we don't clear it, the new process below fails to bind to
rem the port and exits immediately (invisibly, since this window is
rem hidden by launch.vbs) -- the browser then just reopens the OLD
rem process, and it looks like the update never applied. Force-killing
rem whatever's on 5001 first makes every launch start from a clean,
rem up-to-date process.
for /f "tokens=5" %%P in ('netstat -ano ^| findstr "127.0.0.1:5001" ^| findstr "LISTENING"') do (
    echo [INFO] Stopping a previous server instance ^(PID %%P^)...
    taskkill /F /PID %%P >nul 2>nul
)

echo Starting Suno Prompt Generator...
echo Your browser will open automatically in a moment.
echo Close this window to stop the server.
echo.

rem The old version just slept a fixed 2 seconds before opening the browser,
rem not an actual readiness check. The first launch after a reboot (or right
rem after an update reinstalled packages) can take much longer than 2s to
rem start listening -- librosa/numba/scipy are heavy imports, and Windows
rem Defender often real-time-scans freshly written/updated .venv files the
rem first time they're touched. When that happens, the browser opens before
rem Flask is ready, shows a dead page, and the user has to close and relaunch
rem for it to work. Poll the port with curl (bundled with Win10/11) instead,
rem so the browser only opens once the server actually answers (falling back
rem to opening anyway after ~30s so a real startup failure still ends up
rem visible instead of silent).
start /b "" cmd /c "curl.exe -s -o nul --retry 30 --retry-delay 1 --retry-connrefused http://127.0.0.1:5001/ & start http://127.0.0.1:5001"
".venv\Scripts\python.exe" app.py

if errorlevel 1 (
    echo.
    echo [ERROR] The server stopped unexpectedly ^(exit code %errorlevel%^).
    pause
)
