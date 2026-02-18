#!/bin/bash
# ============================================================
#  Radio OS — macOS / Linux Launcher
#  A friendly menu that always greets you the same way.
# ============================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# ── colours (no-op if piped) ─────────────────────────────────
BOLD="\033[1m"; DIM="\033[2m"; RESET="\033[0m"
GREEN="\033[32m"; CYAN="\033[36m"; YELLOW="\033[33m"; RED="\033[31m"

# ── helpers ──────────────────────────────────────────────────

find_python() {
    # Prefer the venv Python if it exists
    if [ -f "radioenv/bin/python" ]; then
        echo "radioenv/bin/python"
        return
    fi
    for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$candidate" &>/dev/null; then
            PY_MINOR=$($candidate -c 'import sys; print(sys.version_info.minor)' 2>/dev/null)
            if [ "$PY_MINOR" -ge 10 ] 2>/dev/null; then
                echo "$candidate"
                return
            fi
        fi
    done
    echo ""
}

ensure_venv() {
    if [ -d "radioenv" ]; then
        source radioenv/bin/activate 2>/dev/null
        return 0
    fi

    PYTHON_CMD=$(find_python)
    if [ -z "$PYTHON_CMD" ]; then
        echo -e "${RED}[!] Python 3.10+ is required but not found.${RESET}"
        echo ""
        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo "    Install via Homebrew:  brew install python@3.12"
            echo "    Or download:           https://www.python.org/downloads/macos/"
        else
            echo "    Ubuntu/Debian: sudo apt install python3.12 python3.12-venv"
            echo "    Fedora:        sudo dnf install python3.12"
        fi
        return 1
    fi

    echo -e "${CYAN}[*] Creating virtual environment with $($PYTHON_CMD --version)...${RESET}"
    $PYTHON_CMD -m venv radioenv
    if [ $? -ne 0 ]; then
        echo -e "${RED}[!] Failed to create venv.${RESET}"
        [[ "$OSTYPE" != "darwin"* ]] && echo "    Try: sudo apt install python3-venv"
        return 1
    fi
    source radioenv/bin/activate
    echo -e "${GREEN}[+] Virtual environment created & activated.${RESET}"
}

# ── 1. Boot Radio OS ────────────────────────────────────────

do_boot() {
    echo ""
    echo -e "${BOLD}  Launching Radio OS...${RESET}"
    echo ""

    if [ ! -d "radioenv" ]; then
        echo -e "${YELLOW}[!] No virtual environment found. Run option 2 first.${RESET}"
        return
    fi

    source radioenv/bin/activate

    # Quick sanity check
    python -c "import yaml, sounddevice" &>/dev/null
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}[!] Some core packages are missing. Run option 2 to install them.${RESET}"
        return
    fi

    python shell_bookmark.py
}

# ── 2. Install core dependencies ────────────────────────────

do_install_core() {
    echo ""
    echo -e "${BOLD}  Installing core dependencies${RESET}"
    echo ""

    ensure_venv || return

    # macOS tkinter check
    if [[ "$OSTYPE" == "darwin"* ]]; then
        python -c "import _tkinter" &>/dev/null
        if [ $? -ne 0 ]; then
            PY_MINOR=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
            echo -e "${CYAN}[*] Installing python-tk@${PY_MINOR} via Homebrew...${RESET}"
            brew install "python-tk@${PY_MINOR}" 2>&1
        fi
    fi

    echo -e "${CYAN}[*] Upgrading pip...${RESET}"
    pip install --upgrade pip -q

    echo -e "${CYAN}[*] Installing requirements.txt (this may take a few minutes)...${RESET}"
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo -e "${RED}[!] Install failed. Check your internet connection.${RESET}"
        [[ "$OSTYPE" != "darwin"* ]] && echo "    You may need: sudo apt install python3-tk libsndfile1 ffmpeg portaudio19-dev"
        return
    fi

    # macOS SDL2 conflict fix (pygame ↔ opencv)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        SITE_PKG="radioenv/lib/python$(python -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')/site-packages"
        CV2_SDL="${SITE_PKG}/cv2/.dylibs/libSDL2-2.0.0.dylib"
        PG_SDL="${SITE_PKG}/pygame/.dylibs/libSDL2-2.0.0.dylib"
        if [ -f "$CV2_SDL" ] && [ ! -L "$CV2_SDL" ] && [ -f "$PG_SDL" ]; then
            echo -e "${CYAN}[*] Fixing SDL2 dylib conflict (pygame ↔ opencv)...${RESET}"
            PG_SDL_ABS="$(cd "$(dirname "$PG_SDL")" && pwd)/$(basename "$PG_SDL")"
            rm "$CV2_SDL"
            ln -s "$PG_SDL_ABS" "$CV2_SDL"
            echo -e "${GREEN}[+] SDL2 conflict resolved.${RESET}"
        fi
    fi

    echo ""
    echo -e "${GREEN}[+] Core dependencies installed successfully!${RESET}"
    echo -e "${DIM}    You can now choose option 1 to boot Radio OS.${RESET}"
}

# ── 3. Install Ollama ───────────────────────────────────────

do_install_ollama() {
    echo ""
    echo -e "${BOLD}  Ollama — Local AI Models${RESET}"
    echo ""
    echo "  Ollama lets you run large-language models on your own machine."
    echo "  This is optional — you can use OpenAI / Claude / Gemini API keys instead."
    echo ""
    echo "  Download size: ~500 MB for Ollama + 4–12 GB per model."
    echo ""
    read -p "  Proceed? (Y/n): " CONFIRM
    [[ ! "$CONFIRM" =~ ^[Yy]?$ ]] && echo "  Skipped." && return

    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo -e "${CYAN}[*] Downloading Ollama for macOS...${RESET}"
        curl --progress-bar -L https://ollama.ai/download/Ollama-darwin.zip -o /tmp/ollama.zip
        if [ $? -eq 0 ]; then
            unzip -qo /tmp/ollama.zip -d /tmp
            [ -d "/tmp/Ollama.app" ] && sudo cp -R /tmp/Ollama.app /Applications/ && echo -e "${GREEN}[+] Ollama installed to /Applications${RESET}"
            open /Applications/Ollama.app 2>/dev/null
            rm -rf /tmp/ollama.zip /tmp/Ollama.app
        else
            echo -e "${RED}[!] Download failed. Get it manually: https://ollama.ai/download${RESET}"
            return
        fi
    else
        echo -e "${CYAN}[*] Installing Ollama for Linux...${RESET}"
        curl -fsSL https://ollama.ai/install.sh | sh
        [ $? -ne 0 ] && echo -e "${RED}[!] Install failed. Try: https://ollama.ai/download${RESET}" && return
    fi

    echo ""
    echo "  Which models would you like to pull?"
    echo "    a) Recommended starter set  (qwen3:8b, llama3.1:8b)           ~8 GB"
    echo "    b) Full set                 (+ deepseek-r1:8b, nomic-embed)  ~16 GB"
    echo "    s) Skip model downloads for now"
    echo ""
    read -p "  Choice (a/b/s): " MODEL_CHOICE

    sleep 3  # let Ollama service start

    case "$MODEL_CHOICE" in
        [Aa])
            echo -e "${CYAN}[*] Pulling qwen3:8b...${RESET}";    ollama pull qwen3:8b
            echo -e "${CYAN}[*] Pulling llama3.1:8b...${RESET}";  ollama pull llama3.1:8b
            ;;
        [Bb])
            echo -e "${CYAN}[*] Pulling qwen3:8b...${RESET}";              ollama pull qwen3:8b
            echo -e "${CYAN}[*] Pulling llama3.1:8b...${RESET}";            ollama pull llama3.1:8b
            echo -e "${CYAN}[*] Pulling deepseek-r1:8b...${RESET}";         ollama pull deepseek-r1:8b
            echo -e "${CYAN}[*] Pulling nomic-embed-text:v1.5...${RESET}";  ollama pull nomic-embed-text:v1.5
            ;;
        *) echo "  Skipped model downloads." ;;
    esac

    echo -e "${GREEN}[+] Ollama setup complete.${RESET}"
}

# ── 4. Install Piper TTS ────────────────────────────────────

do_install_piper() {
    echo ""
    echo -e "${BOLD}  Piper — Offline Text-to-Speech${RESET}"
    echo ""
    echo "  Piper is a free, fast, offline TTS engine."
    echo "  This is optional — Radio OS also supports Kokoro (built-in),"
    echo "  ElevenLabs, and OpenAI TTS."
    echo ""
    echo "  Download size: 20–400 MB depending on voices selected."
    echo ""
    read -p "  Proceed? (Y/n): " CONFIRM
    [[ ! "$CONFIRM" =~ ^[Yy]?$ ]] && echo "  Skipped." && return

    ensure_venv || return

    echo -e "${CYAN}[*] Running Piper setup wizard...${RESET}"
    python setup.py

    # Auto-configure manifests if tool exists
    PIPER_BIN="$(pwd)/voices/piper/piper"
    VOICES_DIR="$(pwd)/voices"
    if [ -f "tools/inject_manifest_paths.py" ]; then
        echo -e "${CYAN}[*] Configuring station manifests...${RESET}"
        python tools/inject_manifest_paths.py --piper-bin "$PIPER_BIN" --voices-dir "$VOICES_DIR" 2>/dev/null
    fi

    echo -e "${GREEN}[+] Piper setup complete.${RESET}"
}

# ── 5. Install PyTorch ──────────────────────────────────────

do_install_pytorch() {
    echo ""
    echo -e "${BOLD}  PyTorch — ML Features${RESET}"
    echo ""
    echo "  PyTorch enables advanced machine-learning features for the"
    echo "  'From the Backmarker' station.  The station works fine without it"
    echo "  (it falls back to simpler AI)."
    echo ""
    echo "  Download size: ~2 GB"
    echo ""
    read -p "  Proceed? (Y/n): " CONFIRM
    [[ ! "$CONFIRM" =~ ^[Yy]?$ ]] && echo "  Skipped." && return

    ensure_venv || return

    echo -e "${CYAN}[*] Installing PyTorch (this may take 5–15 minutes)...${RESET}"
    pip install 'torch>=2.0.0' --progress-bar on
    if [ $? -ne 0 ]; then
        echo -e "${RED}[!] PyTorch install failed. You can try again later.${RESET}"
    else
        echo -e "${GREEN}[+] PyTorch installed — ML features enabled.${RESET}"
    fi
}

# ── Main menu ────────────────────────────────────────────────

while true; do
    echo ""
    echo -e "${BOLD}========================================${RESET}"
    echo -e "${BOLD}        🎙️  Radio OS Launcher${RESET}"
    echo -e "${BOLD}========================================${RESET}"
    echo ""
    echo "  1)  Boot Radio OS"
    echo "  2)  Install / update core dependencies"
    echo "  ─────────────────────────────────────"
    echo "  3)  Install Ollama   (local AI models, optional)"
    echo "  4)  Install Piper    (offline TTS, optional)"
    echo "  5)  Install PyTorch  (ML features, optional)"
    echo ""
    echo "  q)  Quit"
    echo ""
    read -p "  Choose [1-5, q]: " CHOICE

    case "$CHOICE" in
        1) do_boot ;;
        2) do_install_core ;;
        3) do_install_ollama ;;
        4) do_install_piper ;;
        5) do_install_pytorch ;;
        [Qq]) echo ""; echo "  Goodbye!"; echo ""; exit 0 ;;
        *) echo -e "${YELLOW}  Invalid choice. Pick 1-5 or q.${RESET}" ;;
    esac
done
