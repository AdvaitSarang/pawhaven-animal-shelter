@echo off
setlocal
cd /d "%~dp0..\source"
.venv\Scripts\python.exe -m pytest -v ..\test
set RESULT=%ERRORLEVEL%
pause
exit /b %RESULT%
