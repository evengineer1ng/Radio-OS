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

# Piper download URLs (from official Rhasspy releases)
PIPER_URLS = {
    "windows": "https://github.com/rhasspy/piper/releases/download/2024.1.1/piper_windows_amd64.zip",
    "macos_amd64": "https://github.com/rhasspy/piper/releases/download/2024.1.1/piper_macos_amd64.tar.gz",
    "macos_arm64": "https://github.com/rhasspy/piper/releases/download/2024.1.1/piper_macos_arm64.tar.gz",
    "linux": "https://github.com/rhasspy/piper/releases/download/2024.1.1/piper_linux_x86_64.tar.gz",
}

VOICES_INFO = """
Piper Voice Models: https://github.com/rhasspy/piper/blob/master/VOICES.md

Popular voices (CC-BY-NC licensed):
  - en_US-amy-medium.onnx (US English, female)
  - en_US-danny-low.onnx (US English, male)
  - en_GB-alan-medium.onnx (UK English, male)

Download voices from:
  https://huggingface.co/rhasspy/piper-voices/

Each voice needs:
  - model.onnx (voice model)
  - model.onnx.json (metadata)
"""

def download_file(url, dest):
    """Download file with progress indication."""
    print(f"Downloading {os.path.basename(dest)}...")
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"✓ Downloaded to {dest}")
        return True
    except Exception as e:
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
