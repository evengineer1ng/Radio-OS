@echo off
REM ============================================================
REM  Radio OS — Windows Launcher
REM  A friendly menu that always greets you the same way.
REM ============================================================

setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

:menu
echo.
echo ========================================
echo         Radio OS Launcher
echo ========================================
echo.
echo   1)  Boot Radio OS
echo   2)  Install / update core dependencies
echo   -----------------------------------------
echo   3)  Install Ollama   (local AI models, optional)
echo   4)  Install Piper    (offline TTS, optional)
echo   5)  Install PyTorch  (ML features, optional)
echo.
echo   q)  Quit
echo.
set /p CHOICE="  Choose [1-5, q]: "

if "%CHOICE%"=="1" goto :do_boot
if "%CHOICE%"=="2" goto :do_install_core
if "%CHOICE%"=="3" goto :do_install_ollama
if "%CHOICE%"=="4" goto :do_install_piper
if "%CHOICE%"=="5" goto :do_install_pytorch
if /i "%CHOICE%"=="q" goto :quit
echo   Invalid choice. Pick 1-5 or q.
goto :menu

REM ========================================
REM  1. Boot Radio OS
REM ========================================
:do_boot
echo.
echo   Launching Radio OS...
echo.

if not exist "radioenv\" (
    echo   [!] No virtual environment found. Run option 2 first.
    goto :menu
)

call radioenv\Scripts\activate.bat
if errorlevel 1 (
    echo   [!] Failed to activate virtual environment.
    goto :menu
)

python -c "import yaml, sounddevice" >nul 2>&1
if errorlevel 1 (
    echo   [!] Some core packages are missing. Run option 2 to install them.
    goto :menu
)

python shell_bookmark.py
goto :menu

REM ========================================
REM  2. Install core dependencies
REM ========================================
:do_install_core
echo.
echo   Installing core dependencies
echo.

REM --- Check Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo   [!] Python is not installed or not in your PATH.
    echo.
    echo       Radio OS requires Python 3.10 or newer.
    echo       Download: https://www.python.org/downloads/
    echo       IMPORTANT: Check "Add Python to PATH" during installation
    echo.
    goto :menu
)
echo   [+] Python found
echo.

REM --- Create venv ---
if not exist "radioenv\" (
    echo   [*] Creating virtual environment...
    python -m venv radioenv
    if errorlevel 1 (
        echo   [!] Failed to create venv. Ensure Python 3.10+ is installed.
        goto :menu
    )
    echo   [+] Virtual environment created
)

call radioenv\Scripts\activate.bat
if errorlevel 1 (
    echo   [!] Failed to activate virtual environment.
    goto :menu
)
echo   [+] Virtual environment activated
echo.

echo   [*] Upgrading pip...
python -m pip install --upgrade pip -q

echo   [*] Installing requirements.txt (this may take a few minutes)...
pip install -r requirements.txt
if errorlevel 1 (
    echo   [!] Install failed. Check your internet connection.
    goto :menu
)

echo.
echo   [+] Core dependencies installed successfully!
echo       You can now choose option 1 to boot Radio OS.
goto :menu

REM ========================================
REM  3. Install Ollama
REM ========================================
:do_install_ollama
echo.
echo   Ollama — Local AI Models
echo.
echo   Ollama lets you run large-language models on your own machine.
echo   This is optional — you can use OpenAI / Claude / Gemini API keys instead.
echo.
echo   Download size: ~500 MB installer + 4-12 GB per model.
echo.
set /p CONFIRM="  Proceed? (Y/n): "
if /i not "%CONFIRM%"=="Y" if not "%CONFIRM%"=="" (
    echo   Skipped.
    goto :menu
)

echo.
echo   [*] Downloading Ollama installer...
set OLLAMA_INSTALLER=%TEMP%\OllamaSetup.exe

powershell -Command "$ProgressPreference='Continue'; Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile '%OLLAMA_INSTALLER%'"
if errorlevel 1 (
    echo   [!] Download failed. Get it manually: https://ollama.ai/download
    goto :menu
)

echo   [+] Download complete
echo   [*] Running installer...
start /wait "" "%OLLAMA_INSTALLER%" /S
del "%OLLAMA_INSTALLER%" 2>nul
echo   [+] Ollama installed
echo.

echo   Which models would you like to pull?
echo     a) Recommended starter set  (qwen3:8b, llama3.1:8b)           ~8 GB
echo     b) Full set                 (+ deepseek-r1:8b, nomic-embed)  ~16 GB
echo     s) Skip model downloads for now
echo.
set /p MODEL_CHOICE="  Choice (a/b/s): "

timeout /t 3 /nobreak >nul

if /i "%MODEL_CHOICE%"=="a" (
    echo   [*] Pulling qwen3:8b...
    ollama pull qwen3:8b
    echo   [*] Pulling llama3.1:8b...
    ollama pull llama3.1:8b
) else if /i "%MODEL_CHOICE%"=="b" (
    echo   [*] Pulling qwen3:8b...
    ollama pull qwen3:8b
    echo   [*] Pulling llama3.1:8b...
    ollama pull llama3.1:8b
    echo   [*] Pulling deepseek-r1:8b...
    ollama pull deepseek-r1:8b
    echo   [*] Pulling nomic-embed-text:v1.5...
    ollama pull nomic-embed-text:v1.5
) else (
    echo   Skipped model downloads.
)

echo   [+] Ollama setup complete.
goto :menu

REM ========================================
REM  4. Install Piper TTS
REM ========================================
:do_install_piper
echo.
echo   Piper — Offline Text-to-Speech
echo.
echo   Piper is a free, fast, offline TTS engine.
echo   This is optional — Radio OS also supports Kokoro (built-in),
echo   ElevenLabs, and OpenAI TTS.
echo.
echo   Download size: 20-400 MB depending on voices selected.
echo.
set /p CONFIRM="  Proceed? (Y/n): "
if /i not "%CONFIRM%"=="Y" if not "%CONFIRM%"=="" (
    echo   Skipped.
    goto :menu
)

if not exist "radioenv\" (
    echo   [!] Run option 2 first to set up the virtual environment.
    goto :menu
)
call radioenv\Scripts\activate.bat

echo   [*] Running Piper setup wizard...
python setup.py

REM Auto-configure manifests
set PIPER_BIN=%SCRIPT_DIR%voices\piper\piper.exe
set VOICES_DIR=%SCRIPT_DIR%voices
if exist "tools\inject_manifest_paths.py" (
    echo   [*] Configuring station manifests...
    python tools\inject_manifest_paths.py --piper-bin "%PIPER_BIN%" --voices-dir "%VOICES_DIR%" 2>nul
)

echo   [+] Piper setup complete.
goto :menu

REM ========================================
REM  5. Install PyTorch
REM ========================================
:do_install_pytorch
echo.
echo   PyTorch — ML Features
echo.
echo   PyTorch enables advanced machine-learning features for the
echo   "From the Backmarker" station.  The station works fine without it
echo   (it falls back to simpler AI).
echo.
echo   Download size: ~2 GB
echo.
set /p CONFIRM="  Proceed? (Y/n): "
if /i not "%CONFIRM%"=="Y" if not "%CONFIRM%"=="" (
    echo   Skipped.
    goto :menu
)

if not exist "radioenv\" (
    echo   [!] Run option 2 first to set up the virtual environment.
    goto :menu
)
call radioenv\Scripts\activate.bat

echo   [*] Installing PyTorch (this may take 5-15 minutes)...
pip install torch>=2.0.0 --progress-bar on
if errorlevel 1 (
    echo   [!] PyTorch install failed. You can try again later.
) else (
    echo   [+] PyTorch installed — ML features enabled.
)
goto :menu

REM ========================================
:quit
echo.
echo   Goodbye!
echo.
endlocal
exit /b 0
