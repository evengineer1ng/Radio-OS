#!/bin/bash
# Radio OS macOS/Linux Launcher
# Detects first-run vs subsequent runs and handles setup accordingly

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# ========================================
# Check for first-time vs subsequent run
# ========================================

if [ -f ".radio_os_setup_complete" ]; then
    bash -c "$(declare -f subsequent_run); subsequent_run"
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
echo "  3. Download Piper TTS + voice models (optional, ~200-400MB)"
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

# Python check
if ! command -v python3 &> /dev/null; then
    echo "[!] Python 3 is not installed."
    echo ""
    if [[ "$PLATFORM" == "macOS" ]]; then
        echo "[*] Install via Homebrew: brew install python"
        echo "[*] Or download: https://www.python.org/downloads/macos/"
    else
        echo "[*] Install via your package manager:"
        echo "    Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-venv python3-pip"
        echo "    Fedora: sudo dnf install python3"
        echo "    Arch: sudo pacman -S python"
    fi
    exit 1
fi

echo "[+] Python found"
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
    echo "[*] Creating virtual environment..."
    python3 -m venv radioenv
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
        echo "[*] Downloading Ollama for macOS..."
        curl -fsSL https://ollama.ai/download/Ollama-darwin.zip -o /tmp/ollama.zip
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
        echo "[*] Downloading AI models (~8-12GB, 10-30 minutes)..."
        echo "[*] Models: qwen3:8b, llama3.1:8b, deepseek-r1:8b, rnj-1:8b, nomic-embed-text"
        echo ""
        
        sleep 3  # Wait for Ollama service
        
        echo "[*] Pulling qwen3:8b..."
        ollama pull qwen3:8b
        echo ""
        
        echo "[*] Pulling llama3.1:8b..."
        ollama pull llama3.1:8b
        echo ""
        
        echo "[*] Pulling deepseek-r1:8b..."
        ollama pull deepseek-r1:8b
        echo ""
        
        echo "[*] Pulling rnj-1:8b..."
        ollama pull rnj-1:8b
        echo ""
        
        echo "[*] Pulling nomic-embed-text:v1.5..."
        ollama pull nomic-embed-text:v1.5
        echo ""
        
        echo "[+] AI models downloaded successfully"
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
echo ""
echo "Download size: ~200-400MB"
echo ""
echo "Alternative: Skip this and configure ElevenLabs or other"
echo "TTS APIs manually later (see README.md)."
echo ""
read -p "Install Piper + voices now? (Recommended) (Y/n): " INSTALL_PIPER

if [[ "$INSTALL_PIPER" =~ ^[Yy]?$ ]]; then
    echo ""
    echo "[*] Downloading Piper TTS binary..."
    
    # Determine correct Piper download
    if [[ "$PLATFORM" == "macOS" ]]; then
        if [[ "$MACHINE" == "arm64" ]]; then
            PIPER_URL="https://github.com/rhasspy/piper/releases/download/2024.1.1/piper_macos_arm64.tar.gz"
            PIPER_ARCHIVE="piper_macos_arm64.tar.gz"
        else
            PIPER_URL="https://github.com/rhasspy/piper/releases/download/2024.1.1/piper_macos_amd64.tar.gz"
            PIPER_ARCHIVE="piper_macos_amd64.tar.gz"
        fi
    else
        PIPER_URL="https://github.com/rhasspy/piper/releases/download/2024.1.1/piper_linux_x86_64.tar.gz"
        PIPER_ARCHIVE="piper_linux_x86_64.tar.gz"
    fi
    
    curl -L "$PIPER_URL" -o "/tmp/$PIPER_ARCHIVE"
    if [ $? -eq 0 ]; then
        echo "[+] Download complete"
        echo "[*] Extracting Piper..."
        mkdir -p voices
        tar -xzf "/tmp/$PIPER_ARCHIVE" -C voices/
        rm "/tmp/$PIPER_ARCHIVE"
        echo "[+] Piper installed to voices/"
        echo ""
        
        # Download voice models
        echo "[*] Downloading voice models (~200MB, may take 5-10 minutes)..."
        echo "[*] Voices: lessac, alba, danny, amy, hfc_female, southern_english_female, alan"
        echo ""
        
        download_voice() {
            local voice=$1
            echo "  [*] Downloading $voice..."
            curl -s -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/$voice.onnx" -o "voices/$voice.onnx"
            curl -s -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/$voice.onnx.json" -o "voices/$voice.onnx.json"
            if [ $? -eq 0 ]; then
                echo "  [+] $voice downloaded"
            else
                echo "  [!] Warning: Could not download $voice"
            fi
        }
        
        download_voice "en_US-lessac-high"
        download_voice "en_GB-alba-medium"
        download_voice "en_US-danny-low"
        download_voice "en_US-amy-medium"
        download_voice "en_US-hfc_female-medium"
        download_voice "en_GB-southern_english_female-low"
        download_voice "en_GB-alan-medium"
        
        echo ""
        echo "[+] Voice models downloaded successfully"
        echo ""
        
        # Inject paths into manifests
        echo "[*] Configuring station manifests..."
        
        # Find piper binary
        PIPER_BIN=$(find "$SCRIPT_DIR/voices" -name "piper" -type f | head -n 1)
        VOICES_DIR="$SCRIPT_DIR/voices"
        
        python3 tools/inject_manifest_paths.py --piper-bin "$PIPER_BIN" --voices-dir "$VOICES_DIR"
        if [ $? -ne 0 ]; then
            echo "[!] Warning: Manifest path injection failed"
            echo "[!] You may need to manually configure voice paths"
        else
            echo "[+] Station manifests configured"
        fi
    else
        echo "[!] Failed to download Piper"
        echo "[*] Skipping voice setup"
    fi
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
    echo "[*] Installing PyTorch (~2GB download, may take 5-15 minutes)..."
    pip install torch>=2.0.0
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
echo ""
echo "See README.md for more information and troubleshooting."
echo ""
echo "[*] Launching Radio OS Shell..."
echo ""
sleep 2

python3 shell_bookmark.py
exit 0

# ========================================
# SUBSEQUENT RUN
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
    python3 -c "import yaml, sounddevice" &> /dev/null
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
    python3 shell_bookmark.py
}

# If we reach here on subsequent run, call the function
if [ -f ".radio_os_setup_complete" ]; then
    subsequent_run
fi
