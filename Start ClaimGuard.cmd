@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer, then reopen this file.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating the local Python environment...
  python -m venv .venv
  if errorlevel 1 goto failed
)
echo Installing or checking ClaimGuard packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Starting ClaimGuard in a separate server window...
start "ClaimGuard server" cmd /k "echo Starting ClaimGuard Python server... && .venv\Scripts\python.exe -u app.py"
echo Waiting for the website to finish starting. This can take a little while on first launch.
 powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0wait_for_server.ps1"
if errorlevel 1 goto notready
:ready
echo ClaimGuard is responding. Opening the website...
start "" http://127.0.0.1:5000
echo Keep the ClaimGuard server window open. Close it to stop the website.
timeout /t 6
exit /b 0
:notready
echo ClaimGuard did not respond within two minutes. Read the error in the black ClaimGuard server window.
pause
exit /b 1
:failed
echo Setup did not finish. Check the error above; an internet connection is needed for first-time packages.
pause
exit /b 1
