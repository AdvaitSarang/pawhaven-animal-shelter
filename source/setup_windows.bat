@echo off
setlocal
cd /d "%~dp0"
echo Creating a local Python environment...
py -3 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m flask --app shelter init-db
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m flask --app shelter seed-demo
if errorlevel 1 goto failed
echo.
echo Copy the staff credentials above before closing this window.
echo Next, double-click start_windows.bat and open http://127.0.0.1:5000
echo If the seed was skipped, use an existing account or see README.md.
pause
exit /b 0
:failed
echo.
echo Setup stopped. Read the error above. Python 3.12 or later is required.
echo See README.md for troubleshooting.
pause
exit /b 1
