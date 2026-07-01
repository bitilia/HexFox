@echo off
REM HexFox Load Time Comparator - Windows launcher.
REM First run creates a local virtual environment and installs dependencies.
REM Every run after that just launches the app.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [HexFox] Setting up local environment for the first time...
    py -3 -m venv .venv || python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

".venv\Scripts\python.exe" main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [HexFox] The app exited with an error. See above for details.
    pause
)
