@echo off
REM Radio OS Windows Launcher
REM Detects first-run vs subsequent runs and handles setup accordingly

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM ========================================
REM Check for first-time vs subsequent run
REM ========================================

if exist ".radio_os_setup_complete" (
    goto :subsequent_run
) else (
    goto :first_run
)

REM ========================================
REM FIRST-TIME SETUP
REM ========================================
:first_run

echo.
echo ========================================
echo       Radio OS - First Time Setup
echo ========================================
echo.
echo Welcome to Radio OS! This setup will:
echo   1. Install Python dependencies
echo   2. Download Ollama AI models (optional, ~8-12GB)
echo   3. Download Piper TTS + voice models (optional, ~200-400MB)
echo   4. Install PyTorch for ML features (optional, ~2GB)
echo.
echo Total setup may take 15-45 minutes depending on your connection.
echo.

REM Python check
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python is not installed or not in your PATH.
    echo.
    echo [*] Radio OS requires Python 3.10 or newer.
    echo.
    echo     Download: https://www.python.org/downloads/
    echo     IMPORTANT: Check "Add Python to PATH" during installation
    echo.
    echo     Or via winget: winget install -e --id Python.Python.3.11
    echo.
    pause
    exit /b 1
)

echo [+] Python found
echo.

REM User confirmation
set /p PROCEED="You are about to install Python tools to enable Radio OS. Proceed? (Y/n): "
if /i not "%PROCEED%"=="Y" if /i not "%PROCEED%"=="" (
    echo.
    echo Setup cancelled by user.
    pause
    exit /b 0
)

echo.
echo ========================================
echo   Step 1/5: Python Dependencies
echo ========================================
echo.

REM Create venv if needed
if not exist "radioenv\" (
    echo [*] Creating virtual environment...
    python -m venv radioenv
    if errorlevel 1 (
        echo [!] Failed to create venv. Ensure Python 3.10+ is installed.
        pause
        exit /b 1
    )
    echo [+] Virtual environment created
)

REM Activate venv
call radioenv\Scripts\activate.bat
if errorlevel 1 (
    echo [!] Failed to activate virtual environment.
    pause
    exit /b 1
)

echo [+] Virtual environment activated
echo.
echo [*] Installing dependencies (this may take a few minutes)...
python -m pip install --upgrade pip -q
pip install -r requirements.txt
if errorlevel 1 (
    echo [!] Failed to install dependencies.
    echo [!] Check your internet connection and try again.
    pause
    exit /b 1
)

echo [+] Dependencies installed successfully
echo.

REM ========================================
REM Step 2: Ollama Setup
REM ========================================
echo ========================================
echo   Step 2/5: Ollama AI Models
echo ========================================
echo.
echo Ollama is free AI Large Language Model software which runs on
echo your GPU locally. It enables Radio OS stations to generate content.
echo.
echo Download size: ~8-12GB (may take 10-30 minutes)
echo.
echo Alternative: Skip this and manually configure ChatGPT, Claude,
echo or Gemini API keys later (see README.md for details).
echo.
set /p INSTALL_OLLAMA="Install Ollama + AI models now? (Y/n): "

if /i "%INSTALL_OLLAMA%"=="Y" (
    goto :install_ollama
) else if /i "%INSTALL_OLLAMA%"=="" (
    goto :install_ollama
) else (
    echo [*] Skipping Ollama installation
    echo [!] You'll need to configure alternative AI endpoints manually
    goto :skip_ollama
)

:install_ollama
echo.
echo [*] Downloading Ollama installer (~500MB)...
echo [*] This may take 2-5 minutes depending on your connection
set OLLAMA_INSTALLER=%TEMP%\OllamaSetup.exe

REM Download Ollama using PowerShell with progress
powershell -Command "$ProgressPreference = 'SilentlyContinue'; Write-Host '  Downloading from https://ollama.ai/download/OllamaSetup.exe'; $URI = 'https://ollama.ai/download/OllamaSetup.exe'; $OutFile = '%OLLAMA_INSTALLER%'; try { $response = Invoke-WebRequest -Uri $URI -OutFile $OutFile -PassThru -UseBasicParsing; Write-Host '  [+] Download complete' -ForegroundColor Green } catch { Write-Host '  [!] Download failed: ' $_.Exception.Message -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
    echo [!] Failed to download Ollama installer
    echo [!] You can manually download from: https://ollama.ai/download
    goto :skip_ollama
)

echo [+] Download complete
echo [*] Installing Ollama (this may take a moment)...

REM Run installer silently
start /wait "" "%OLLAMA_INSTALLER%" /S
if errorlevel 1 (
    echo [!] Ollama installation may have failed
    echo [!] Try manual installation: https://ollama.ai/download
    goto :skip_ollama
)

REM Clean up installer
del "%OLLAMA_INSTALLER%" 2>nul

echo [+] Ollama installed successfully
echo.
echo ========================================
echo   Downloading AI Models (~8-12GB)
echo ========================================
echo [*] This is the largest download and may take 10-30 minutes
echo [*] Ollama will show its own progress bars for each model
echo [*] Models: qwen3:8b, llama3.1:8b, deepseek-r1:8b, rnj-1:8b, nomic-embed-text
echo.

REM Wait a moment for Ollama service to start
echo [*] Starting Ollama service...
timeout /t 5 /nobreak >nul
echo.

REM Pull essential models
echo [*] Model 1/5: Pulling qwen3:8b...
ollama pull qwen3:8b
echo.

echo [*] Model 2/5: Pulling llama3.1:8b...
ollama pull llama3.1:8b
echo.

echo [*] Model 3/5: Pulling deepseek-r1:8b...
ollama pull deepseek-r1:8b
echo.

echo [*] Model 4/5: Pulling rnj-1:8b...
ollama pull rnj-1:8b
echo.

echo [*] Model 5/5: Pulling nomic-embed-text:v1.5...
ollama pull nomic-embed-text:v1.5
echo.

echo [+] All AI models downloaded successfully

:skip_ollama
echo.

REM ========================================
REM Step 3: Piper TTS Setup
REM ========================================
echo ========================================
echo   Step 3/5: Piper Text-to-Speech
echo ========================================
echo.
echo Piper is free text-to-speech software. Radio OS uses it to
echo generate voice audio for station hosts and characters.
echo.
echo Download size: ~200-400MB
echo.
echo Alternative: Skip this and configure ElevenLabs or other
echo TTS APIs manually later (see README.md).
echo.
set /p INSTALL_PIPER="Install Piper + voices now? (Recommended) (Y/n): "

if /i "%INSTALL_PIPER%"=="Y" (
    goto :install_piper
) else if /i "%INSTALL_PIPER%"=="" (
    goto :install_piper
) else (
    echo [*] Skipping Piper installation
    echo [!] Stations will not have audio without TTS configured
    goto :skip_piper
)

:install_piper
echo.
echo [*] Downloading Piper TTS binary (~50MB)...
echo [*] This should take 1-2 minutes
set PIPER_ZIP=%TEMP%\piper_windows.zip
set PIPER_URL=https://github.com/rhasspy/piper/releases/download/2024.1.1/piper_windows_amd64.zip

REM Download with progress indication
powershell -Command "$ProgressPreference = 'SilentlyContinue'; Write-Host '  Downloading from GitHub...'; try { Invoke-WebRequest -Uri '%PIPER_URL%' -OutFile '%PIPER_ZIP%' -UseBasicParsing; Write-Host '  [+] Download complete' -ForegroundColor Green } catch { Write-Host '  [!] Download failed: ' $_.Exception.Message -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
    echo [!] Failed to download Piper
    goto :skip_piper
)

echo [+] Download complete
echo [*] Extracting Piper...

if not exist "voices\" mkdir voices
powershell -Command "& {Expand-Archive -Path '%PIPER_ZIP%' -DestinationPath 'voices\' -Force}"
if errorlevel 1 (
    echo [!] Failed to extract Piper
    del "%PIPER_ZIP%" 2>nul
    goto :skip_piper
)

del "%PIPER_ZIP%" 2>nul
echo [+] Piper installed to voices\piper_windows_amd64\
echo.

REM Download voice models
echo [*] Downloading voice models (~200MB, may take 5-10 minutes)...
echo [*] Voices: lessac, alba, danny, amy, hfc_female, southern_english_female, alan
echo.

REM Helper function for downloading voices
call :download_voice en_US-lessac-high
call :download_voice en_GB-alba-medium
call :download_voice en_US-danny-low
call :download_voice en_US-amy-medium
call :download_voice en_US-hfc_female-medium
call :download_voice en_GB-southern_english_female-low
call :download_voice en_GB-alan-medium

echo.
echo [+] Voice models downloaded successfully
echo.

REM Inject paths into station manifests
echo [*] Configuring station manifests...
set PIPER_BIN=%SCRIPT_DIR%voices\piper_windows_amd64\piper\piper.exe
set VOICES_DIR=%SCRIPT_DIR%voices

python tools\inject_manifest_paths.py --piper-bin "%PIPER_BIN%" --voices-dir "%VOICES_DIR%"
if errorlevel 1 (
    echo [!] Warning: Manifest path injection failed
    echo [!] You may need to manually configure voice paths
) else (
    echo [+] Station manifests configured
)

:skip_piper
echo.

REM ========================================
REM Step 4: PyTorch (Optional ML)
REM ========================================
echo ========================================
echo   Step 4/5: PyTorch ML Features
echo ========================================
echo.
echo PyTorch enables advanced ML features for the "From the Backmarker"
echo station (AI-powered team management and decision making).
echo.
echo Download size: ~2GB
echo.
echo The station works without PyTorch using simpler AI. This is
echo optional and only needed if you want ML-powered features.
echo.
set /p INSTALL_PYTORCH="Install PyTorch now? (Y/n): "

if /i "%INSTALL_PYTORCH%"=="Y" (
    goto :install_pytorch
) else if /i "%INSTALL_PYTORCH%"=="" (
    goto :install_pytorch
) else (
    echo [*] Skipping PyTorch installation
    echo [*] From the Backmarker will use basic AI (you can install later with: pip install torch)
    goto :skip_pytorch
)

:install_pytorch
echo.
echo ========================================
echo   PyTorch Installation (~2GB Download)
echo ========================================
echo [*] This is a large package that will take 5-15 minutes
echo [*] You'll see progress bars from pip - this is normal!
echo [*] Download speed depends on your internet connection
echo.
echo [*] Starting PyTorch installation...
echo.
pip install torch>=2.0.0 --progress-bar on
if errorlevel 1 (
    echo [!] PyTorch installation failed
    echo [*] Continuing without PyTorch (From the Backmarker will use basic AI)
) else (
    echo [+] PyTorch installed - FTB ML features enabled
)

:skip_pytorch
echo.

REM ========================================
REM Finalize Setup
REM ========================================
echo ========================================
echo   Step 5/5: Finalizing Setup
echo ========================================
echo.
echo [*] Creating setup completion marker...
echo Setup completed on %date% %time% > .radio_os_setup_complete

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo Radio OS is ready to launch. You can now:
echo   - Launch stations from the Radio OS Shell
echo   - Create custom stations in the stations/ directory
echo   - Configure additional feeds and plugins
echo.
echo See README.md for more information and troubleshooting.
echo.
echo [*] Launching Radio OS Shell...
echo.
timeout /t 3 /nobreak >nul

python shell_bookmark.py
goto :eof

REM ========================================
REM SUBSEQUENT RUN
REM ========================================
:subsequent_run

echo.
echo ========================================
echo       Radio OS Launcher
echo ========================================
echo.

REM Activate venv
if not exist "radioenv\" (
    echo [!] Virtual environment missing! Re-run first-time setup.
    del .radio_os_setup_complete
    goto :first_run
)

call radioenv\Scripts\activate.bat
if errorlevel 1 (
    echo [!] Failed to activate virtual environment.
    pause
    exit /b 1
)

REM Quick dependency check
python -c "import yaml, sounddevice" >nul 2>&1
if errorlevel 1 (
    echo [!] Dependencies check failed. Some packages may be missing.
    echo.
    set /p REINSTALL="Reinstall dependencies now? (Y/n): "
    if /i "%REINSTALL%"=="Y" (
        goto :reinstall_deps
    ) else if /i "%REINSTALL%"=="" (
        goto :reinstall_deps
    ) else (
        echo [*] Continuing without reinstall (may cause errors)
    )
)

goto :launch_shell

:reinstall_deps
echo.
echo [*] Reinstalling dependencies...
python -m pip install --upgrade pip -q
pip install -r requirements.txt
if errorlevel 1 (
    echo [!] Reinstall failed. Check your internet connection.
    pause
    exit /b 1
)
echo [+] Dependencies reinstalled

:launch_shell
echo [*] Launching Radio OS Shell...
echo.
python shell_bookmark.py

endlocal
goto :eof

REM ========================================
REM HELPER FUNCTIONS
REM ========================================

REM Download a Piper voice model
:download_voice
set VOICE_NAME=%1
set BASE_URL=https://huggingface.co/rhasspy/piper-voices/resolve/main
echo   [*] Downloading %VOICE_NAME%... (this may take 30-60 seconds)
powershell -Command "$ProgressPreference = 'SilentlyContinue'; try { Write-Host '      - Downloading model file...' -ForegroundColor Gray; Invoke-WebRequest -Uri '%BASE_URL%/%VOICE_NAME%.onnx' -OutFile 'voices\%VOICE_NAME%.onnx' -UseBasicParsing; Write-Host '      - Downloading config file...' -ForegroundColor Gray; Invoke-WebRequest -Uri '%BASE_URL%/%VOICE_NAME%.onnx.json' -OutFile 'voices\%VOICE_NAME%.onnx.json' -UseBasicParsing; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo   [!] Warning: Could not download %VOICE_NAME%
) else (
    echo   [+] %VOICE_NAME% downloaded
)
goto :eof
