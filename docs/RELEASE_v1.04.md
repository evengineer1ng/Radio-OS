# Radio OS v1.04 Release Notes

**Release Date:** February 11, 2026
**Version:** 1.04
**Codename:** Environment Master

## 🎉 Major Features

### Environment Variables Configuration GUI
- **New Settings Panel**: Added comprehensive Environment Variables tab in the desktop GUI
- **File Browser Integration**: Click-to-browse for directory paths (STATION_DIR, RADIO_OS_PLUGINS, etc.)
- **Secure API Key Handling**: Masked input fields for sensitive tokens and keys
- **Real-time Validation**: Instant feedback on configuration validity
- **Station Launcher Integration**: Direct launch with custom environment settings

### Enhanced macOS Setup
- **Robust Python Detection**: Auto-detects Python 3.10+ across all Homebrew versions
- **Automatic tkinter Installation**: Resolves missing `_tkinter` module on clean macOS installs
- **SDL2 Conflict Resolution**: Eliminates duplicate class warnings between pygame and opencv
- **Improved Error Handling**: Clear diagnostics for setup failures

## 🔧 Technical Improvements

### Setup Script (`mac.sh`)
- Fixed unreachable bash function ordering
- Added comprehensive Python version detection loop
- Integrated Homebrew python-tk auto-installation
- Implemented SDL2 dylib conflict resolution via symlinks
- Enhanced error reporting and user guidance

### Dependencies (`requirements.txt`)
- Fixed PyObjC package names (`pyobjc-framework-Cocoa` vs non-existent `AppKit`)
- Switched to headless OpenCV to prevent SDL2 conflicts
- Verified all packages install cleanly on macOS arm64

### GUI Application (`shell_bookmark.py`)
- Added Environment Variables settings tab with intuitive interface
- Implemented file browser dialogs for path selection
- Added secure API key input with masking
- Integrated version display in application title
- Enhanced station launcher with environment variable support

## 🐛 Bug Fixes

- **SDL2 Warnings**: Resolved "Class X is implemented in both Y and Z" warnings
- **tkinter Import**: Fixed `ModuleNotFoundError: No module named '_tkinter'` on fresh installs
- **Package Names**: Corrected non-existent PyObjC framework references
- **Setup Script**: Fixed bash function ordering that prevented proper execution

## 🎯 User Experience

### Simplified Configuration
- No more manual environment variable editing
- Visual file browsers replace error-prone path typing
- Immediate validation prevents configuration mistakes
- Secure handling of sensitive API credentials

### Streamlined Setup
- Single-command setup for new users
- Automatic dependency resolution
- Clear error messages with solution guidance
- Cross-platform compatibility (macOS/Linux)

## 📋 System Requirements

- **Python**: 3.10+ (auto-detected and installed)
- **macOS**: 10.15+ with Homebrew
- **Linux**: Modern distributions with tkinter support
- **Memory**: 2GB RAM minimum for audio processing
- **Storage**: 1GB for models and voice files

## 🚀 Getting Started

1. **Fresh Installation**:
   ```bash
   git clone <radio-os-repo>
   cd Radio-OS-1.03
   chmod +x mac.sh
   ./mac.sh
   ```

2. **Existing Users**:
   - Update your repository
   - Run the desktop GUI to access new Environment Variables settings
   - Configure your preferred directories and API keys

3. **Environment Configuration**:
   - Launch Radio OS desktop GUI
   - Navigate to "Environment Variables" tab
   - Set paths using file browsers
   - Configure API keys with masked input
   - Click "Launch Station" to test configuration

## 🔗 Integration Notes

This release maintains full backward compatibility while adding powerful new configuration options. Existing stations and plugins continue to work without modification.

The new environment variable system integrates seamlessly with the existing station launcher and manifest system, providing a bridge between user configuration and runtime execution.

---

**Download**: Radio-OS-1.03 (GitHub)
**Documentation**: See `documentation/USER_GUIDE.md`
**Support**: Check existing issues or create new ones on GitHub