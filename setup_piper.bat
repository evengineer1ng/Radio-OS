@echo off
REM setup_piper.bat - Windows Batch Piper Setup Helper
REM Quick standalone Piper + Voice setup for Windows users

echo 🎙️  Radio OS - Piper TTS Setup (Windows)
echo ==================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python is not installed or not in your PATH.
    echo.
    echo     Radio OS requires Python 3.10 or newer.
    echo     Download: https://www.python.org/downloads/
    echo     IMPORTANT: Check "Add Python to PATH" during installation
    echo.
    echo     Or via winget: winget install Python.Python.3.11
    echo.
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [+] Python found: %%v
)

echo.
echo [*] Starting enhanced Piper setup...
echo     This will download Piper TTS 2023.11.14-2 with interactive voice selection
echo.

REM Run the main setup script
python setup.py
if errorlevel 1 (
    echo.
    echo [!] Setup failed. Please check the error above.
    echo.
    echo     Try running manually: python setup.py
    echo.
    pause
    exit /b 1
)

echo.
echo [+] Setup completed successfully!
echo.
echo Next steps:
echo   1. Launch Radio OS: python shell_bookmark.py
echo   2. Configure voice paths in station manifests  
echo   3. Test TTS in any station!
echo.
pause