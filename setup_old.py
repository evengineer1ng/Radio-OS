#!/usr/bin/env python3
"""
Radio OS Setup Helper
Downloads Piper TTS binary and voice models for your platform.
"""
import os
import sys
import platform
import urllib.request
import zipfile
import tarfile
import json

RADIO_OS_ROOT = os.path.dirname(os.path.abspath(__file__))
VOICES_DIR = os.path.join(RADIO_OS_ROOT, "voices")

# Platform detection
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

print("Radio OS Setup Helper")
print("=" * 50)
print(f"Platform: {platform.system()} ({platform.machine()})")
print(f"Python: {sys.version}")

# Piper download URLs (Updated to 2023.11.14-2 release)
PIPER_URLS = {
    "windows": "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip",
    "macos_amd64": "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_macos_x64.tar.gz",
    "macos_arm64": "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_macos_aarch64.tar.gz",
    "linux": "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz",
}

# Voice models to download
VOICE_MODELS = {
    "en_US-lessac-high": {
        "name": "Lessac (US English, Female, High Quality)",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx.json",
        "size": "~45MB"
    },
    "en_US-danny-low": {
        "name": "Danny (US English, Male, Low Quality)",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/danny/low/en_US-danny-low.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/danny/low/en_US-danny-low.onnx.json",
        "size": "~17MB"
    },
    "en_US-hfc_female-medium": {
        "name": "HFC Female (US English, Female, Medium Quality)",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx.json",
        "size": "~25MB"
    },
    "en_GB-alan-medium": {
        "name": "Alan (UK English, Male, Medium Quality)",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json",
        "size": "~25MB"
    },
    "en_GB-southern_english_female-low": {
        "name": "Southern English Female (UK English, Female, Low Quality)",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/southern_english_female/low/en_GB-southern_english_female-low.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/southern_english_female/low/en_GB-southern_english_female-low.onnx.json",
        "size": "~17MB"
    },
    "en_GB-alba-medium": {
        "name": "Alba (UK English, Female, Medium Quality)",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json",
        "size": "~25MB"
    },
    "eminem": {
        "name": "Eminem (Celebrity Voice, Experimental)",
        "onnx": "https://github.com/simoniz0r/piper-voice-models/releases/download/eminem/eminem.onnx",
        "json": "https://github.com/simoniz0r/piper-voice-models/releases/download/eminem/eminem.onnx.json",
        "size": "~63MB"
    }
}

def _download_progress_hook(count, block_size, total_size):
    """Progress callback for urllib.request.urlretrieve."""
    if total_size > 0:
        percent = min(int(count * block_size * 100 / total_size), 100)
        downloaded_mb = (count * block_size) / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        bar_length = 50
        filled_length = int(bar_length * percent / 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        speed_indicator = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'][count % 10]
        print(f"\r  {speed_indicator} [{bar}] {percent}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)", end='', flush=True)
    else:
        # Indeterminate progress when size is unknown
        spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'][count % 10]
        downloaded_mb = (count * block_size) / (1024 * 1024)
        print(f"\r  {spinner} Downloading... ({downloaded_mb:.1f} MB)", end='', flush=True)

def download_file(url, dest):
    """Download file with progress indication."""
    filename = os.path.basename(dest)
    print(f"\nDownloading {filename}...")
    print(f"  Source: {url}")
    print(f"  Destination: {dest}")
    print()
    try:
        urllib.request.urlretrieve(url, dest, reporthook=_download_progress_hook)
        print()  # New line after progress bar
        print(f"✓ Downloaded successfully")
        return True
    except Exception as e:
        print()  # New line after progress bar
        print(f"✗ Download failed: {e}")
        return False

def extract_zip(archive, dest):
    """Extract ZIP archive."""
    print(f"Extracting {os.path.basename(archive)}...")
    try:
        with zipfile.ZipFile(archive, 'r') as z:
            z.extractall(dest)
        print(f"✓ Extracted to {dest}")
        os.remove(archive)
        return True
    except Exception as e:
        print(f"✗ Extraction failed: {e}")
        return False

def extract_tar(archive, dest):
    """Extract TAR archive."""
    print(f"Extracting {os.path.basename(archive)}...")
    try:
        with tarfile.open(archive, 'r:gz') as t:
            t.extractall(dest)
        print(f"✓ Extracted to {dest}")
        os.remove(archive)
        return True
    except Exception as e:
        print(f"✗ Extraction failed: {e}")
        return False

def setup_piper():
    """Download and setup Piper binary for current platform."""
    print("\nSetting up Piper TTS...")
    print("-" * 50)
    
    os.makedirs(VOICES_DIR, exist_ok=True)
    
    if IS_WINDOWS:
        url = PIPER_URLS["windows"]
        dest = os.path.join(VOICES_DIR, "piper_windows_amd64.zip")
        if download_file(url, dest):
            extract_zip(dest, VOICES_DIR)
            print("✓ Piper Windows setup complete")
            return True
    
    elif IS_MAC:
        machine = platform.machine()
        if machine == "arm64":
            url = PIPER_URLS["macos_arm64"]
            dest = os.path.join(VOICES_DIR, "piper_macos_arm64.tar.gz")
        else:
            url = PIPER_URLS["macos_amd64"]
            dest = os.path.join(VOICES_DIR, "piper_macos_amd64.tar.gz")
        
        if download_file(url, dest):
            extract_tar(dest, VOICES_DIR)
            print("✓ Piper macOS setup complete")
            return True
    
    elif IS_LINUX:
        url = PIPER_URLS["linux"]
        dest = os.path.join(VOICES_DIR, "piper_linux_x86_64.tar.gz")
        if download_file(url, dest):
            extract_tar(dest, VOICES_DIR)
            print("✓ Piper Linux setup complete")
            return True
    
    print("✗ Unsupported platform")
    return False

if __name__ == "__main__":
    print("\nThis setup script will:")
    print("1. Download Piper TTS binary for your platform")
    print("2. Extract it to voices/")
    print("\nNote: Voice models must be downloaded separately from:")
    print("  https://huggingface.co/rhasspy/piper-voices/")
    print("\n" + VOICES_INFO)
    
    response = input("\nProceed with setup? (y/n): ").strip().lower()
    if response != 'y':
        print("Setup cancelled.")
        sys.exit(0)
    
    if setup_piper():
        print("\n✓ Setup complete! Next steps:")
        print("  1. Download voice models from HuggingFace Piper Voices")
        print("  2. Extract .onnx and .onnx.json files to voices/")
        print("  3. Run: python shell.py")
    else:
        print("\n✗ Setup failed. See errors above.")
        sys.exit(1)
