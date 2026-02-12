# Radio OS Changelog

## Version 1.04 (February 11, 2026)

### 🚀 Major Features

**Environment Variables Settings Panel**
- Added comprehensive Environment Variables tab in Settings
- GUI configuration for all Radio OS environment variables
- File browser support for path variables
- Show/hide toggle for sensitive API keys
- Auto-detection of current values and reset functionality

### 🔧 Improvements

**macOS Setup Enhancements**
- Intelligent Python version detection (3.10+ required)
- Auto-detection of best available Python (3.13 → 3.12 → 3.11 → 3.10)
- Automatic `python-tk` installation via Homebrew
- Clear error messages for Python version requirements

**Dependency Management**
- Fixed `pyobjc-framework-AppKit` → `pyobjc-framework-Cocoa` (correct PyPI package)
- Switched to `opencv-python-headless` to eliminate SDL2 conflicts
- Automatic SDL2 dylib conflict resolution on macOS
- Fixed PyTorch installation with proper shell quoting

**Setup Script Improvements**
- Fixed unreachable `subsequent_run` function
- Better error handling and user feedback
- Proper Python executable selection throughout script
- Enhanced tkinter availability checks

### 🛠️ Technical Changes

**Environment Variable Integration**
- Station launcher now applies environment variables from global config
- Environment variables persist across restarts
- Secure storage of API keys in global configuration
- Plugin access to configured environment variables

**Code Quality**
- Added version constants and display
- Improved error handling in setup scripts
- Better cross-platform compatibility
- Enhanced documentation

### 📚 Documentation

- Added comprehensive Environment Variables section to README
- Created example plugin demonstrating environment variable usage
- Added demo script for checking current environment configuration
- Updated troubleshooting documentation

### 🐛 Bug Fixes

- Resolved SDL2 duplicate class warnings on macOS
- Fixed Python version detection edge cases
- Corrected package name for PyObjC AppKit framework
- Fixed shell script syntax and quoting issues

---

## Version 1.03 (Previous Release)

Initial stable release with core Radio OS functionality.