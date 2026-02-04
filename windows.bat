@echo off
REM Radio OS Windows Launcher
REM Sets up venv, installs deps, validates setup, launches shell

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo.
echo ========================================
echo Radio OS Windows Launcher
echo ========================================
echo.

REM Verify Python installation and version
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [!] Python is not installed or not in your PATH.
    echo.
    echo [*] Radio OS requires Python 3.10 or newer.
    echo.
    echo     1. Download it here: https://www.python.org/downloads/
    echo     2. IMPORTANT: Check the box "Add Python to PATH" during installation.
    echo.
    echo     Alternatively, if you have winget installed:
    echo     winget install -e --id Python.Python.3.11
    echo.
    pause
    exit /b 1
)

REM Check if venv exists
if not exist "radioenv\" (
    echo [*] Creating virtual environment...
    python -m venv radioenv
    if errorlevel 1 (
        echo [!] Failed to create venv. Ensure Python 3.10+ is installed.
        pause
        exit /b 1
    )
)

REM Activate venv
call radioenv\Scripts\activate.bat
if errorlevel 1 (
    echo [!] Failed to activate venv.
    pause
    exit /b 1
)

REM Upgrade pip and install dependencies
echo [*] Checking dependencies...
python -m pip install --upgrade pip -q
pip install -r requirements.txt
if errorlevel 1 (
    echo [!] Failed to install dependencies.
    pause
    exit /b 1
)

REM Optional: Check for FFMPEG (needed for some audio plugins)
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [!] Warning: ffmpeg not found in PATH.
    echo [!] Some audio processing features (pydub) may not work.
    echo [!] Install from: https://ffmpeg.org/download.html
    echo. 
)

REM Check if Piper is set up
if not exist "voices\piper_windows_amd64\piper\piper.exe" (
    echo [!] Piper TTS not found. Running setup...
    python setup.py
    if errorlevel 1 (
        echo [!] Setup failed or was cancelled.
        pause
        exit /b 1
    )
)

REM Check if voice models exist
for %%f in (voices\*.onnx) do goto voice_found
echo [!] No voice models found in voices\ directory.
echo [*] Visit: https://huggingface.co/rhasspy/piper-voices/
echo [*] Download .onnx and .onnx.json files to voices\
pause
goto skip_voice_check
:voice_found
echo [+] Voice models found
:skip_voice_check

REM Launch shell
echo.
echo [+] Setup complete! Launching Radio OS Shell...
echo.
python shell.py

endlocal
