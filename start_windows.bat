@echo off
setlocal

cd /d "%~dp0"
echo Installing requirements...
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install requirements.
  pause
  exit /b 1
)

echo Starting app on http://127.0.0.1:5000
py app.py

echo.
echo App stopped.
pause
