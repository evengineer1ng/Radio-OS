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

# Check if venv exists
if [ ! -d "radioenv" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv radioenv
    if [ $? -ne 0 ]; then
        echo "[!] Failed to create venv. Ensure Python 3.10+ is installed."
        exit 1
    fi
fi

# Activate venv
source radioenv/bin/activate
if [ $? -ne 0 ]; then
    echo "[!] Failed to activate venv."
    exit 1
fi

# Install/update dependencies
echo "[*] Installing dependencies..."
pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[!] Failed to install dependencies."
    exit 1
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
