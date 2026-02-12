#!/usr/bin/env python3
"""
Radio OS Setup Helper - Enhanced Piper & Voices Installer
Downloads Piper TTS binary and voice models with interactive selection.
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

print("🎙️  Radio OS Piper TTS Setup")
print("=" * 50)
print(f"Platform: {platform.system()} ({platform.machine()})")
print(f"Python: {sys.version}")

# Updated Piper URLs (2023.11.14-2 release)
PIPER_URLS = {
    "windows": "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip",
    "macos_amd64": "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_macos_x64.tar.gz",
    "macos_arm64": "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_macos_aarch64.tar.gz",
    "linux": "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz",
}

# Curated voice collection
VOICE_MODELS = {
    "en_US-lessac-high": {
        "name": "Lessac (US English, Female, High Quality)",
        "description": "Professional female voice with clear pronunciation",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx.json",
        "size": "~45MB",
        "recommended": True
    },
    "en_US-danny-low": {
        "name": "Danny (US English, Male, Fast)",
        "description": "Casual male voice, smaller download",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/danny/low/en_US-danny-low.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/danny/low/en_US-danny-low.onnx.json",
        "size": "~17MB",
        "recommended": True
    },
    "en_US-hfc_female-medium": {
        "name": "HFC Female (US English, Female, Natural)",
        "description": "Smooth female voice with natural cadence",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx.json",
        "size": "~25MB"
    },
    "en_GB-alan-medium": {
        "name": "Alan (UK English, Male, Professional)",
        "description": "British male voice with clear diction",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json",
        "size": "~25MB"
    },
    "en_GB-southern_english_female-low": {
        "name": "Southern English Female (UK English, Female, Fast)",
        "description": "British female voice, smaller download",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/southern_english_female/low/en_GB-southern_english_female-low.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/southern_english_female/low/en_GB-southern_english_female-low.onnx.json",
        "size": "~17MB"
    },
    "en_GB-alba-medium": {
        "name": "Alba (UK English, Female, Scottish)",
        "description": "Scottish-accented female voice",
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json",
        "size": "~25MB"
    },
    "eminem": {
        "name": "Eminem (Celebrity Voice, Experimental)",
        "description": "AI recreation of Eminem's voice (community contribution)",
        "onnx": "https://github.com/simoniz0r/piper-voice-models/releases/download/eminem/eminem.onnx",
        "json": "https://github.com/simoniz0r/piper-voice-models/releases/download/eminem/eminem.onnx.json",
        "size": "~63MB",
        "experimental": True
    }
}

def _download_progress_hook(count, block_size, total_size):
    """Enhanced progress display with visual bar."""
    if total_size > 0:
        percent = min(int(count * block_size * 100 / total_size), 100)
        downloaded_mb = (count * block_size) / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        
        # Visual progress bar
        bar_length = 40
        filled_length = int(bar_length * percent / 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        # Spinning indicator
        spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'][count % 10]
        
        print(f"\\r  {spinner} [{bar}] {percent}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)", end='', flush=True)
    else:
        # Indeterminate progress
        spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'][count % 10]
        downloaded_mb = (count * block_size) / (1024 * 1024)
        print(f"\\r  {spinner} Downloading... ({downloaded_mb:.1f} MB)", end='', flush=True)

def download_file(url, dest):
    """Download file with enhanced progress display."""
    filename = os.path.basename(dest)
    print(f"\\n📥 Downloading {filename}")
    print(f"   From: {url}")
    
    try:
        urllib.request.urlretrieve(url, dest, reporthook=_download_progress_hook)
        print()  # New line after progress
        print(f"   ✅ Downloaded: {filename}")
        return True
    except Exception as e:
        print()
        print(f"   ❌ Download failed: {e}")
        return False

def download_voice_model(voice_id, voice_info):
    """Download both .onnx and .onnx.json files for a voice."""
    print(f"\\n🎤 Installing {voice_info['name']}")
    print(f"   Size: {voice_info['size']} | Description: {voice_info['description']}")
    
    onnx_file = os.path.join(VOICES_DIR, f"{voice_id}.onnx")
    json_file = os.path.join(VOICES_DIR, f"{voice_id}.onnx.json")
    
    # Skip if already exists
    if os.path.exists(onnx_file) and os.path.exists(json_file):
        print(f"   ⏭️  Already installed: {voice_id}")
        return True
    
    # Download model file
    if not download_file(voice_info["onnx"], onnx_file):
        return False
    
    # Download metadata
    if not download_file(voice_info["json"], json_file):
        return False
    
    print(f"   ✅ Voice ready: {voice_id}")
    return True

def extract_archive(archive_path, dest_dir):
    """Extract ZIP or TAR archive with progress."""
    filename = os.path.basename(archive_path)
    print(f"\\n📦 Extracting {filename}")
    
    try:
        if archive_path.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as z:
                z.extractall(dest_dir)
        elif archive_path.endswith(('.tar.gz', '.tgz')):
            with tarfile.open(archive_path, 'r:gz') as t:
                t.extractall(dest_dir)
        else:
            print(f"   ❌ Unknown archive format: {filename}")
            return False
        
        print(f"   ✅ Extracted to: {dest_dir}")
        os.remove(archive_path)  # Clean up archive
        return True
        
    except Exception as e:
        print(f"   ❌ Extraction failed: {e}")
        return False

def setup_piper():
    """Download and setup Piper binary."""
    print("\\n[1/2] 🔧 Setting up Piper TTS Binary")
    print("-" * 60)
    
    os.makedirs(VOICES_DIR, exist_ok=True)
    
    # Determine platform and URL
    if IS_WINDOWS:
        url = PIPER_URLS["windows"]
        archive_name = "piper_windows_amd64.zip"
    elif IS_MAC:
        machine = platform.machine()
        if machine == "arm64":
            url = PIPER_URLS["macos_arm64"]
            archive_name = "piper_macos_arm64.tar.gz"
        else:
            url = PIPER_URLS["macos_amd64"]  
            archive_name = "piper_macos_amd64.tar.gz"
    elif IS_LINUX:
        url = PIPER_URLS["linux"]
        archive_name = "piper_linux_x86_64.tar.gz"
    else:
        print("   ❌ Unsupported platform")
        return False
    
    # Download and extract
    archive_path = os.path.join(VOICES_DIR, archive_name)
    
    if download_file(url, archive_path):
        if extract_archive(archive_path, VOICES_DIR):
            print("\\n   ✅ Piper TTS binary ready!")
            return True
    
    return False

def setup_voices():
    """Interactive voice model setup."""
    print("\\n[2/2] 🎵 Setting up Voice Models")
    print("-" * 60)
    
    # Show available voices
    print("\\nAvailable voices:")
    print()
    
    recommended_voices = []
    other_voices = []
    
    for voice_id, voice_info in VOICE_MODELS.items():
        if voice_info.get("recommended"):
            recommended_voices.append((voice_id, voice_info))
        else:
            other_voices.append((voice_id, voice_info))
    
    # Display recommended first
    if recommended_voices:
        print("🌟 Recommended voices:")
        for i, (voice_id, voice_info) in enumerate(recommended_voices, 1):
            marker = "⭐" if voice_info.get("recommended") else "🔬" if voice_info.get("experimental") else "  "
            print(f"   {i}. {marker} {voice_info['name']} ({voice_info['size']})")
            print(f"      {voice_info['description']}")
            print()
    
    # Display other voices
    if other_voices:
        start_num = len(recommended_voices) + 1
        print("🔬 Other voices:")
        for i, (voice_id, voice_info) in enumerate(other_voices, start_num):
            marker = "⭐" if voice_info.get("recommended") else "🔬" if voice_info.get("experimental") else "  "
            print(f"   {i}. {marker} {voice_info['name']} ({voice_info['size']})")
            print(f"      {voice_info['description']}")
            print()
    
    # Menu options
    total_voices = len(VOICE_MODELS)
    print(f"   {total_voices + 1}. 📦 Download all voices")
    print(f"   {total_voices + 2}. ⚡ Quick setup (recommended voices only)")
    print(f"   {total_voices + 3}. ⏭️  Skip voice download")
    
    # Get user choice
    while True:
        try:
            choice = input(f"\\nSelect option (1-{total_voices + 3}): ").strip()
            
            if choice == str(total_voices + 1):
                # Download all
                print("\\n📦 Installing all voices...")
                success = True
                for voice_id, voice_info in VOICE_MODELS.items():
                    if not download_voice_model(voice_id, voice_info):
                        success = False
                return success
            
            elif choice == str(total_voices + 2):
                # Quick setup - recommended only
                print("\\n⚡ Quick setup: Installing recommended voices...")
                success = True
                for voice_id, voice_info in VOICE_MODELS.items():
                    if voice_info.get("recommended"):
                        if not download_voice_model(voice_id, voice_info):
                            success = False
                return success
            
            elif choice == str(total_voices + 3):
                # Skip
                print("\\n⏭️  Skipping voice download.")
                print("   You can run this script again later to add voices.")
                return True
            
            else:
                # Download specific voice
                choice_num = int(choice) - 1
                voice_ids = list(VOICE_MODELS.keys())
                
                if 0 <= choice_num < len(voice_ids):
                    voice_id = voice_ids[choice_num]
                    voice_info = VOICE_MODELS[voice_id]
                    return download_voice_model(voice_id, voice_info)
                else:
                    print("❌ Invalid choice. Please try again.")
        
        except ValueError:
            print("❌ Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\\n\\n⚠️  Setup cancelled by user.")
            return False

def find_piper_binary():
    """Locate Piper binary in installation."""
    search_paths = [
        os.path.join(VOICES_DIR, "piper", "piper"),  # Unix
        os.path.join(VOICES_DIR, "piper", "piper.exe"),  # Windows
        os.path.join(VOICES_DIR, "piper.exe"),  # Windows direct
    ]
    
    for path in search_paths:
        if os.path.isfile(path):
            return os.path.abspath(path)
    return None

def list_installed_voices():
    """Find all installed voice models."""
    if not os.path.exists(VOICES_DIR):
        return []
    
    voices = []
    for filename in os.listdir(VOICES_DIR):
        if filename.endswith('.onnx'):
            voice_id = filename[:-5]  # Remove .onnx extension
            json_path = os.path.join(VOICES_DIR, f"{voice_id}.onnx.json")
            if os.path.exists(json_path):
                voices.append(voice_id)
    return sorted(voices)

if __name__ == "__main__":
    print("\\n🎙️  Radio OS Piper TTS Setup")
    print("=" * 60)
    print("This installer will:")
    print("  1. Download Piper TTS binary (2023.11.14-2)")
    print("  2. Let you choose and download voice models")
    print("  3. Configure environment paths")
    
    # Calculate total download size
    total_size_mb = 25  # Piper binary ~25MB
    for voice_info in VOICE_MODELS.values():
        size_str = voice_info['size'].replace('~', '').replace('MB', '')
        try:
            total_size_mb += int(size_str)
        except:
            pass
    
    print(f"\\n📊 Download info:")
    print(f"   • Piper binary: ~25MB")
    print(f"   • Individual voices: 17-63MB each")
    print(f"   • All voices total: ~{total_size_mb}MB")
    print(f"   • Installation path: {VOICES_DIR}")
    
    # Confirm setup
    while True:
        response = input("\\n🚀 Continue with setup? (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            break
        elif response in ['n', 'no']:
            print("Setup cancelled.")
            sys.exit(0)
        else:
            print("Please enter 'y' or 'n'")
    
    # Step 1: Piper binary
    if not setup_piper():
        print("\\n❌ Failed to setup Piper binary.")
        sys.exit(1)
    
    # Step 2: Voice models
    if not setup_voices():
        print("\\n❌ Voice setup failed or cancelled.")
        sys.exit(1)
    
    # Final summary
    print("\\n" + "=" * 60)
    print("🎉 Setup Complete!")
    print("=" * 60)
    
    piper_binary = find_piper_binary()
    installed_voices = list_installed_voices()
    
    if piper_binary:
        print(f"✅ Piper binary: {piper_binary}")
        # Make executable on Unix
        if not IS_WINDOWS:
            try:
                import stat
                os.chmod(piper_binary, os.stat(piper_binary).st_mode | stat.S_IEXEC)
                print("   🔧 Made executable")
            except:
                pass
    else:
        print("⚠️  Piper binary not found - check voices/ directory")
    
    if installed_voices:
        print(f"\\n✅ Installed {len(installed_voices)} voice models:")
        for voice in installed_voices:
            voice_info = VOICE_MODELS.get(voice)
            if voice_info:
                marker = "⭐" if voice_info.get("recommended") else "🔬" if voice_info.get("experimental") else "🎤"
                print(f"   {marker} {voice}")
            else:
                print(f"   🎤 {voice}")
    else:
        print("⚠️  No voices installed")
    
    print(f"\\n🚀 Next steps:")
    print(f"   1. Launch Radio OS: python shell_bookmark.py")
    print(f"   2. Go to Settings → Environment Variables")
    if piper_binary:
        print(f"   3. Set PIPER_BIN to: {piper_binary}")
    print(f"   4. Set RADIO_OS_VOICES to: {VOICES_DIR}")
    print(f"   5. Test TTS in any station!")
    
    print(f"\\n📚 Voice info:")
    print(f"   • Voice models are in: {VOICES_DIR}")
    print(f"   • Add more voices anytime by running this script again")
    print(f"   • Browse voices: https://huggingface.co/rhasspy/piper-voices/")