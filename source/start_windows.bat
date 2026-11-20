@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:5000 in your browser.
echo Keep this window open. Press Ctrl+C here to stop the application.
.venv\Scripts\python.exe -m flask --app shelter run --host 127.0.0.1 --port 5000
pause
