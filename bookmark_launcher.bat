@echo off
REM Radio OS Bookmark Shell Launcher
REM Simple launcher that activates venv and runs shell_bookmark.py

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo.
echo ========================================
echo   Radio OS Bookmark Shell
echo ========================================
echo.

REM Check if venv exists
if not exist "radioenv\Scripts\activate.bat" (
    echo [!] Virtual environment not found!
    echo [!] Please run windows.bat first to complete setup.
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
call radioenv\Scripts\activate.bat
if errorlevel 1 (
    echo [!] Failed to activate virtual environment.
    echo.
    pause
    exit /b 1
)

echo [+] Virtual environment activated
echo [*] Starting Radio OS Bookmark Shell...
echo.

REM Run shell_bookmark.py
python shell_bookmark.py

REM Keep window open if there's an error
if errorlevel 1 (
    echo.
    echo [!] Shell exited with an error.
    pause
)

endlocal
