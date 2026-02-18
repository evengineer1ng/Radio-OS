# Radio OS v1.05 - Enhanced Cross-Platform TTS Setup

## 🌍 Universal Piper TTS Setup System

Radio OS v1.05 introduces a completely redesigned, cross-platform Piper TTS setup experience that makes getting high-quality voices easier than ever across Windows, macOS, and Linux.

## ✨ New Features

### Interactive Voice Selection Menu
- **7+ Curated Voices**: From professional female (Lessac) to British accents (Alan, Alba) to experimental (Eminem)
- **Smart Recommendations**: ⭐ marks recommended voices with size and quality info
- **Bulk Options**: Download all voices, recommended only, or quick setup
- **Size Indicators**: See download sizes before selecting (~17MB to ~63MB per voice)

### Beautiful Progress System
- **Visual Progress Bars**: See download progress with animated bars and percentages
- **Spinner Animations**: Elegant loading indicators during downloads
- **Real-time Status**: Download speed and completion feedback
- **Error Handling**: Clear error messages and recovery options

### Cross-Platform Excellence
- **Windows**: Enhanced `.bat` files + standalone PowerShell/batch scripts
- **macOS**: Updated shell scripts with ARM64/x64 detection
- **Linux**: Full compatibility with automatic platform detection
- **Smart Binary Detection**: Handles `.exe` vs regular executables automatically

## 🔧 Technical Improvements

### Updated Piper Integration
- **Latest Piper TTS**: Updated to 2023.11.14-2 release
- **Correct URLs**: Fixed GitHub release URLs and HuggingFace voice paths
- **Proper Directory Structure**: Voices download to correct paths with metadata
- **Automatic Permissions**: Unix executables made executable automatically

### Enhanced Setup Scripts
- **Unified Experience**: All platforms now use the same `setup.py` core
- **Standalone Options**: `setup_piper.bat` and `setup_piper.ps1` for Windows-only setup
- **Intelligent Fallbacks**: Manual configuration guidance if automatic setup fails
- **Repository Optimization**: Large binaries excluded via enhanced `.gitignore`

### Voice Collection Highlights
- **🌟 Recommended Voices**:
  - **Lessac** (US Female, High Quality) - Professional broadcaster voice
  - **Danny** (US Male, Fast) - Casual, smaller download
- **🔬 Additional Voices**:
  - **HFC Female** (US Female, Natural) - Smooth natural cadence
  - **Alan** (UK Male, Professional) - Clear British diction
  - **Alba** (UK Female, Scottish) - Scottish-accented voice
  - **Southern English Female** (UK Female, Fast) - British, compact
- **🎭 Experimental**:
  - **Eminem** (Celebrity Voice) - AI recreation (community contribution)

## 📋 Installation & Usage

### Quick Start (All Platforms)
```bash
# Download and run setup
python setup.py
```

### Windows Users
```batch
# Run enhanced Windows setup
windows.bat

# Or standalone Piper setup
setup_piper.bat
setup_piper.ps1
```

### macOS/Linux Users
```bash
# Run enhanced setup script  
./mac.sh

# Or direct Python setup
python setup.py
```

## 🚀 Next Steps After Setup

1. **Launch Radio OS**: `python shell_bookmark.py`
2. **Configure Environment Variables**:
   - Set `PIPER_BIN` to your Piper binary path
   - Set `RADIO_OS_VOICES` to your voices directory
3. **Test TTS**: Try voice generation in any station
4. **Add More Voices**: Run `python setup.py` again anytime

## 📚 Technical Details

### System Requirements
- **Python**: 3.10+ recommended
- **Storage**: 20MB-400MB for voices (varies by selection)
- **Network**: Internet connection for initial download
- **Platforms**: Windows 10+, macOS 10.14+, Linux (most distributions)

### Voice Model Information
- **Format**: ONNX neural network models
- **Quality**: 22kHz sample rate, high-quality synthesis
- **Languages**: Primarily English (US/UK variants)
- **Source**: [HuggingFace Piper Voices](https://huggingface.co/rhasspy/piper-voices/)

### Integration Points
- **Station Manifests**: Automatic path injection for seamless integration
- **Environment Variables**: Standard `PIPER_BIN` and `RADIO_OS_VOICES` support
- **Audio Pipeline**: Compatible with existing Radio OS audio architecture

## 🔄 Migration from Previous Versions

Existing Radio OS installations can upgrade seamlessly:

1. **Backup existing voices** (optional): Your current voice setup will be preserved
2. **Run new setup**: `python setup.py` will detect existing installations
3. **Enhanced experience**: Enjoy the new interactive interface and additional voices
4. **No breaking changes**: Existing station configurations remain compatible

## 🐛 Bug Fixes & Improvements

- **Fixed Piper Download URLs**: Updated to working 2023.11.14-2 release links
- **Corrected Voice Paths**: HuggingFace URLs now use proper directory structure
- **Enhanced Error Handling**: Better feedback when downloads fail
- **Improved Platform Detection**: More reliable Windows/macOS/Linux detection
- **Streamlined Setup Flow**: Reduced manual configuration steps

## 📖 Documentation & Support

- **Setup Guide**: Enhanced instructions in README.md
- **Voice Browser**: Browse all available voices at [HuggingFace](https://huggingface.co/rhasspy/piper-voices/)
- **Troubleshooting**: Clear error messages and recovery guidance
- **Community**: Join discussions and share station creations

---

## 🎉 What's Next?

Radio OS v1.05 establishes a solid foundation for high-quality TTS across all platforms. Future versions will continue expanding voice options, improving audio quality, and enhancing the overall Radio OS experience.

**Download Radio OS v1.05 today** and give your stations professional-quality voices with just a few clicks!

---

*Radio OS - Create AI-powered radio stations with realistic voices, dynamic content, and immersive audio experiences.*