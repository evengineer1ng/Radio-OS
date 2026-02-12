#!/bin/bash
# Radio OS macOS/Linux Launcher
# Detects first-run vs subsequent runs and handles setup accordingly

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# ========================================
# SUBSEQUENT RUN (defined first so it's callable)
# ========================================
subsequent_run() {
    echo ""
    echo "========================================"
    echo "      Radio OS Launcher"
    echo "========================================"
    echo ""
    
    # Check venv
    if [ ! -d "radioenv" ]; then
        echo "[!] Virtual environment missing! Re-run first-time setup."
        rm -f .radio_os_setup_complete
        exec "$0"
    fi
    
    # Activate venv
    source radioenv/bin/activate
    if [ $? -ne 0 ]; then
        echo "[!] Failed to activate virtual environment."
        exit 1
    fi
    
    # Quick dependency check
    python -c "import yaml, sounddevice" &> /dev/null
    if [ $? -ne 0 ]; then
        echo "[!] Dependencies check failed. Some packages may be missing."
        echo ""
        read -p "Reinstall dependencies now? (Y/n): " REINSTALL
        if [[ "$REINSTALL" =~ ^[Yy]?$ ]]; then
            echo ""
            echo "[*] Reinstalling dependencies..."
            pip install --upgrade pip -q
            pip install -r requirements.txt
            if [ $? -ne 0 ]; then
                echo "[!] Reinstall failed. Check your internet connection."
                exit 1
            fi
            echo "[+] Dependencies reinstalled"
        else
            echo "[*] Continuing without reinstall (may cause errors)"
        fi
    fi
    
    echo "[*] Launching Radio OS Shell..."
    echo ""
    python shell_bookmark.py
}

# ========================================
# Check for first-time vs subsequent run
# ========================================

if [ -f ".radio_os_setup_complete" ]; then
    subsequent_run
    exit $?
fi

# ========================================
# FIRST-TIME SETUP
# ========================================

echo ""
echo "========================================"
echo "     Radio OS - First Time Setup"
echo "========================================"
echo ""
echo "Welcome to Radio OS! This setup will:"
echo "  1. Install Python dependencies"
echo "  2. Download Ollama AI models (optional, ~8-12GB)"
echo "  3. Download Piper TTS + voice models (optional, ~20-400MB)"
echo "  4. Install PyTorch for ML features (optional, ~2GB)"
echo ""
echo "Total setup may take 15-45 minutes depending on your connection."
echo ""

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLATFORM="macOS"
    MACHINE=$(uname -m)
else
    PLATFORM="Linux"
    MACHINE=$(uname -m)
fi

echo "[*] Detected platform: $PLATFORM ($MACHINE)"
echo ""

# Python check — require 3.10+ for pyobjc and other modern deps
PYTHON_CMD=""
for candidate in python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" &> /dev/null; then
        PYTHON_CMD="$candidate"
        break
    fi
done
# Fall back to python3 only if it is >= 3.10
if [ -z "$PYTHON_CMD" ]; then
    if command -v python3 &> /dev/null; then
        PY_VER=$(python3 -c 'import sys; print(sys.version_info.minor)')
        if [ "$PY_VER" -ge 10 ] 2>/dev/null; then
            PYTHON_CMD="python3"
        fi
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "[!] Python 3.10 or newer is required but not found."
    echo "    Your default python3 is $(python3 --version 2>&1), which is too old."
    echo ""
    if [[ "$PLATFORM" == "macOS" ]]; then
        echo "[*] Install via Homebrew: brew install python@3.12"
        echo "[*] Or download: https://www.python.org/downloads/macos/"
    else
        echo "[*] Install via your package manager:"
        echo "    Ubuntu/Debian: sudo apt update && sudo apt install python3.12 python3.12-venv"
        echo "    Fedora: sudo dnf install python3.12"
        echo "    Arch: sudo pacman -S python"
    fi
    exit 1
fi

echo "[+] Python found: $($PYTHON_CMD --version)"
echo ""

# User confirmation
read -p "You are about to install Python tools to enable Radio OS. Proceed? (Y/n): " PROCEED
if [[ ! "$PROCEED" =~ ^[Yy]?$ ]]; then
    echo ""
    echo "Setup cancelled by user."
    exit 0
fi

echo ""
echo "========================================"
echo "  Step 1/5: Python Dependencies"
echo "========================================"
echo ""

# Create venv if needed
if [ ! -d "radioenv" ]; then
    echo "[*] Creating virtual environment with $($PYTHON_CMD --version)..."
    $PYTHON_CMD -m venv radioenv
    if [ $? -ne 0 ]; then
        echo "[!] Failed to create venv. Ensure Python 3.10+ is installed."
        if [[ "$PLATFORM" == "Linux" ]]; then
            echo "[!] On Linux: sudo apt-get install python3-venv"
        fi
        exit 1
    fi
    echo "[+] Virtual environment created"
fi

# Activate venv
source radioenv/bin/activate
if [ $? -ne 0 ]; then
    echo "[!] Failed to activate virtual environment."
    exit 1
fi

echo "[+] Virtual environment activated"
echo ""

# macOS: check tkinter availability and install python-tk if needed
if [[ "$PLATFORM" == "macOS" ]]; then
    python -c "import _tkinter" &> /dev/null
    if [ $? -ne 0 ]; then
        PY_MINOR=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        echo "[!] tkinter not available for Python ${PY_MINOR}."
        echo "[*] Installing python-tk@${PY_MINOR} via Homebrew..."
        brew install "python-tk@${PY_MINOR}" 2>&1
        if [ $? -ne 0 ]; then
            echo "[!] Failed to install python-tk@${PY_MINOR}."
            echo "[!] Please install manually: brew install python-tk@${PY_MINOR}"
            echo "[!] Radio OS requires tkinter for its desktop UI."
            exit 1
        fi
        # Verify it works after install
        python -c "import _tkinter" &> /dev/null
        if [ $? -ne 0 ]; then
            echo "[!] tkinter still not working after install."
            echo "[!] Try: brew reinstall python@${PY_MINOR} python-tk@${PY_MINOR}"
            exit 1
        fi
        echo "[+] tkinter configured successfully"
    fi
fi

echo "[*] Installing dependencies (this may take a few minutes)..."
pip install --upgrade pip -q
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[!] Failed to install dependencies."
    if [[ "$PLATFORM" == "Linux" ]]; then
        echo "[!] You may need system packages:"
        echo "    sudo apt-get install python3-tk libsndfile1 ffmpeg portaudio19-dev"
    fi
    exit 1
fi

echo "[+] Dependencies installed successfully"
echo ""

# Fix SDL2 dylib conflict between pygame and opencv on macOS
# Both packages bundle libSDL2; symlinking deduplicates the ObjC class registrations
if [[ "$PLATFORM" == "macOS" ]]; then
    SITE_PKG="radioenv/lib/python$(python -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')/site-packages"
    CV2_SDL="${SITE_PKG}/cv2/.dylibs/libSDL2-2.0.0.dylib"
    PG_SDL="${SITE_PKG}/pygame/.dylibs/libSDL2-2.0.0.dylib"
    if [ -f "$CV2_SDL" ] && [ ! -L "$CV2_SDL" ] && [ -f "$PG_SDL" ]; then
        echo "[*] Fixing SDL2 dylib conflict (pygame ↔ opencv)..."
        PG_SDL_ABS="$(cd "$(dirname "$PG_SDL")" && pwd)/$(basename "$PG_SDL")"
        rm "$CV2_SDL"
        ln -s "$PG_SDL_ABS" "$CV2_SDL"
        echo "[+] SDL2 conflict resolved"
    fi
fi

# ========================================
# Step 2: Ollama Setup
# ========================================
echo "========================================"
echo "  Step 2/5: Ollama AI Models"
echo "========================================"
echo ""
echo "Ollama is free AI Large Language Model software which runs on"
echo "your GPU locally. It enables Radio OS stations to generate content."
echo ""
echo "Download size: ~8-12GB (may take 10-30 minutes)"
echo ""
echo "Alternative: Skip this and manually configure ChatGPT, Claude,"
echo "or Gemini API keys later (see README.md for details)."
echo ""
read -p "Install Ollama + AI models now? (Y/n): " INSTALL_OLLAMA

if [[ "$INSTALL_OLLAMA" =~ ^[Yy]?$ ]]; then
    echo ""
    if [[ "$PLATFORM" == "macOS" ]]; then
        echo "[*] Downloading Ollama for macOS (~500MB)..."
        echo "[*] This may take 2-5 minutes depending on your connection"
        curl --progress-bar -L https://ollama.ai/download/Ollama-darwin.zip -o /tmp/ollama.zip
        if [ $? -eq 0 ]; then
            echo "[+] Download complete"
            echo "[*] Extracting and installing..."
            unzip -q /tmp/ollama.zip -d /tmp
            if [ -d "/tmp/Ollama.app" ]; then
                sudo cp -R /tmp/Ollama.app /Applications/
                echo "[+] Ollama installed to /Applications"
                open /Applications/Ollama.app
                sleep 5
            fi
            rm -rf /tmp/ollama.zip /tmp/Ollama.app
        else
            echo "[!] Download failed. Manual install: https://ollama.ai/download"
            echo "[*] Skipping model download"
            INSTALL_OLLAMA="n"
        fi
    else
        echo "[*] Installing Ollama for Linux..."
        curl -fsSL https://ollama.ai/install.sh | sh
        if [ $? -ne 0 ]; then
            echo "[!] Installation failed. Try manual: https://ollama.ai/download"
            INSTALL_OLLAMA="n"
        else
            echo "[+] Ollama installed"
        fi
    fi
    
    if [[ "$INSTALL_OLLAMA" =~ ^[Yy]?$ ]]; then
        echo ""
        echo "========================================"
        echo "  Downloading AI Models (~8-12GB)"
        echo "========================================"
        echo "[*] This is the largest download and may take 10-30 minutes"
        echo "[*] Ollama will show its own progress bars for each model"
        echo "[*] Models: qwen3:8b, llama3.1:8b, deepseek-r1:8b, rnj-1:8b, nomic-embed-text"
        echo ""
        
        echo "[*] Starting Ollama service..."
        sleep 3  # Wait for Ollama service
        echo ""
        
        echo "[*] Model 1/5: Pulling qwen3:8b..."
        ollama pull qwen3:8b
        echo ""
        
        echo "[*] Model 2/5: Pulling llama3.1:8b..."
        ollama pull llama3.1:8b
        echo ""
        
        echo "[*] Model 3/5: Pulling deepseek-r1:8b..."
        ollama pull deepseek-r1:8b
        echo ""
        
        echo "[*] Model 4/5: Pulling rnj-1:8b..."
        ollama pull rnj-1:8b
        echo ""
        
        echo "[*] Model 5/5: Pulling nomic-embed-text:v1.5..."
        ollama pull nomic-embed-text:v1.5
        echo ""
        
        echo "[+] All AI models downloaded successfully"
    fi
else
    echo "[*] Skipping Ollama installation"
    echo "[!] You'll need to configure alternative AI endpoints manually"
fi

echo ""

# ========================================
# Step 3: Piper TTS Setup
# ========================================
echo "========================================"
echo "  Step 3/5: Piper Text-to-Speech"
echo "========================================"
echo ""
echo "Piper is free text-to-speech software. Radio OS uses it to"
echo "generate voice audio for station hosts and characters."
echo "Our enhanced setup provides an interactive voice selection menu."
echo ""
echo "Download size: ~20-400MB depending on voice selection"
echo ""
echo "Alternative: Skip this and configure ElevenLabs or other"
echo "TTS APIs manually later (see README.md)."
echo ""
read -p "Install Piper + voices now? (Recommended) (Y/n): " INSTALL_PIPER

if [[ "$INSTALL_PIPER" =~ ^[Yy]?$ ]]; then
    echo ""
    echo "[*] Running enhanced Piper TTS setup..."
    echo "[*] This will download Piper 2023.11.14-2 + voice models with interactive selection"
    echo ""
    
    # Run the enhanced Python setup script
    "$PYTHON_CMD" setup.py
    if [ $? -eq 0 ]; then
        echo ""
        echo "[+] Enhanced Piper setup completed successfully"
        
        # Set up environment variables
        echo "[*] Configuring environment variables..."
        PIPER_BIN="$(pwd)/voices/piper/piper"
        VOICES_DIR="$(pwd)/voices"
        
        # Inject paths into station manifests if tools are available
        if [ -f "tools/inject_manifest_paths.py" ]; then
            echo "[*] Configuring station manifests..."
            "$PYTHON_CMD" tools/inject_manifest_paths.py --piper-bin "$PIPER_BIN" --voices-dir "$VOICES_DIR"
            if [ $? -eq 0 ]; then
                echo "[+] Station manifests configured"
            else
                echo "[!] Warning: Manifest path injection failed"
                echo "[!] You may need to manually configure voice paths"
            fi
        else
            echo "[*] Manual setup: Set PIPER_BIN=$PIPER_BIN in your station manifests"
        fi
    else
        echo "[!] Enhanced Piper setup failed"
        echo "[!] You can try running 'python setup.py' manually later"
else
    echo "[*] Skipping Piper installation"
    echo "[!] Stations will not have audio without TTS configured"
fi

echo ""

# ========================================
# Step 4: PyTorch (Optional ML)
# ========================================
echo "========================================"
echo "  Step 4/5: PyTorch ML Features"
echo "========================================"
echo ""
echo "PyTorch enables advanced ML features for the 'From the Backmarker'"
echo "station (AI-powered team management and decision making)."
echo ""
echo "Download size: ~2GB"
echo ""
echo "The station works without PyTorch using simpler AI. This is"
echo "optional and only needed if you want ML-powered features."
echo ""
read -p "Install PyTorch now? (Y/n): " INSTALL_PYTORCH

if [[ "$INSTALL_PYTORCH" =~ ^[Yy]?$ ]]; then
    echo ""
    echo "========================================"
    echo "  PyTorch Installation (~2GB Download)"
    echo "========================================"
    echo "[*] This is a large package that will take 5-15 minutes"
    echo "[*] You'll see progress bars from pip - this is normal!"
    echo "[*] Download speed depends on your internet connection"
    echo ""
    echo "[*] Starting PyTorch installation..."
    echo ""
    pip install 'torch>=2.0.0' --progress-bar on
    if [ $? -ne 0 ]; then
        echo "[!] PyTorch installation failed"
        echo "[*] Continuing without PyTorch (From the Backmarker will use basic AI)"
    else
        echo "[+] PyTorch installed - FTB ML features enabled"
    fi
else
    echo "[*] Skipping PyTorch installation"
    echo "[*] From the Backmarker will use basic AI (install later with: pip install torch)"
fi

echo ""

# ========================================
# Finalize Setup
# ========================================
echo "========================================"
echo "  Step 5/5: Finalizing Setup"
echo "========================================"
echo ""
echo "[*] Creating setup completion marker..."
echo "Setup completed on $(date)" > .radio_os_setup_complete

echo ""
echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo ""
echo "Radio OS is ready to launch. You can now:"
echo "  - Launch stations from the Radio OS Shell"
echo "  - Create custom stations in the stations/ directory"
echo "  - Configure additional feeds and plugins"
echo "  - Set environment variables in Settings > Environment"
echo ""
echo "See README.md for more information and troubleshooting."
echo ""
echo "[*] Launching Radio OS Shell..."
echo ""
sleep 2

python shell_bookmark.py
exit 0
