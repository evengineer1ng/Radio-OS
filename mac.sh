#!/bin/bash
# Radio OS macOS/Linux Launcher
# Sets up venv, installs deps, validates setup, launches shell

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo ""
echo "========================================"
echo "Radio OS Unix Launcher"
echo "========================================"
echo ""

# Check Python availability
if ! command -v python3 &> /dev/null; then
    echo ""
    echo "[!] Python 3 is not installed."
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "[*] Quick fix (if you have Homebrew):"
        echo "    brew install python"
        echo ""
        echo "[*] Or download the installer: https://www.python.org/downloads/macos/"
    else
        echo "[*] Install via your package manager:"
        echo "    Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-venv python3-pip"
        echo "    Fedora: sudo dnf install python3"
        echo "    Arch: sudo pacman -S python"
    fi
    exit 1
fi

# Check if venv exists
if [ ! -d "radioenv" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv radioenv
    if [ $? -ne 0 ]; then
        echo "[!] Failed to create venv. Ensure Python 3.10+ is installed (and python3-venv on Linux)."
        exit 1
    fi
fi

# Activate venv
source radioenv/bin/activate
if [ $? -ne 0 ]; then
    echo "[!] Failed to activate venv."
    exit 1
fi

# Upgrade pip and install dependencies
echo "[*] Checking dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[!] Failed to install dependencies."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "[!] Hint: On Linux, you may need system packages:"
        echo "    sudo apt-get install python3-tk libsndfile1 ffmpeg portaudio19-dev"
    fi
    exit 1
fi

# Check for FFMPEG
if ! command -v ffmpeg &> /dev/null; then
    echo "[!] Warning: ffmpeg not found."
    echo "[!] Some audio plugins may require it."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "    Install via Homebrew: brew install ffmpeg"
    else
        echo "    Install via apt: sudo apt install ffmpeg"
    fi
    echo ""
fi

# Detect platform
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    PIPER_PATHS=(
        "voices/piper_macos_arm64/piper/piper"
        "voices/piper_macos_amd64/piper/piper"
    )
    PLATFORM="macOS"
else
    # Linux
    PIPER_PATHS=(
        "voices/piper_linux_x86_64/piper/piper"
        "voices/piper_linux_amd64/piper/piper"
    )
    PLATFORM="Linux"
fi

# Check if Piper is set up
PIPER_FOUND=0
for piper_path in "${PIPER_PATHS[@]}"; do
    if [ -f "$piper_path" ]; then
        PIPER_FOUND=1
        break
    fi
done

if [ $PIPER_FOUND -eq 0 ]; then
    echo "[!] Piper TTS not found. Running setup..."
    python setup.py
    if [ $? -ne 0 ]; then
        echo "[!] Setup failed or was cancelled."
        exit 1
    fi
fi

# Check if voice models exist
if ls voices/*.onnx 1> /dev/null 2>&1; then
    echo "[+] Voice models found"
else
    echo "[!] No voice models found in voices/ directory."
    echo "[*] Visit: https://huggingface.co/rhasspy/piper-voices/"
    echo "[*] Download .onnx and .onnx.json files to voices/"
    echo ""
    read -p "Press Enter to continue anyway (or Ctrl+C to exit)..."
fi

# Launch shell
echo ""
echo "[+] Setup complete! Launching Radio OS Shell..."
echo ""
python shell.py
