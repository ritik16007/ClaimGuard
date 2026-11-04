@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run Start ClaimGuard.cmd once so the local Python environment is prepared.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" setup_local_ai.py
if errorlevel 1 (
  echo Local AI setup failed. Check the last error above and keep this window open while it runs.
  pause
  exit /b 1
)
echo Local AI is ready. Close and reopen ClaimGuard to use the upgraded assistant.
pause
