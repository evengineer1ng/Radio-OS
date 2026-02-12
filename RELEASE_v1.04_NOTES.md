# Radio OS v1.04 - "Environment Master" 🎛️

**Release Date:** February 12, 2026  
**Major Release** - Enhanced macOS Support + Environment Configuration GUI

## 🎉 Major Features

### 🎛️ Environment Variables Configuration GUI
- **Visual Settings Panel**: New Environment Variables tab in Radio OS Shell
- **File Browser Integration**: Click-to-browse for directory paths (RADIO_OS_PLUGINS, RADIO_OS_VOICES, etc.)
- **Secure API Key Management**: Masked input fields with show/hide toggles for sensitive credentials
- **Real-time Validation**: Instant feedback on configuration validity
- **Station Launcher Integration**: Direct launch with custom environment settings

### 🍎 Enhanced macOS Setup
- **Robust Python Detection**: Auto-detects Python 3.10+ across all Homebrew versions (python3.13→3.10)
- **Automatic tkinter Installation**: Resolves missing `_tkinter` module via Homebrew `python-tk`
- **SDL2 Conflict Resolution**: Eliminates duplicate class warnings between pygame and opencv
- **Improved Error Handling**: Clear diagnostics and user guidance for setup failures

### 🌐 FTB Web Interface (From PC)
- **Svelte Frontend**: Modern web interface for From the Backmarker station management
- **Real-time Dashboard**: Live race operations, team management, and analytics
- **Web Server Plugin**: `ftb_web_server.py` with WebSocket support
- **Multi-tab Interface**: Race ops, team management, development, analytics, and more

## 🔧 Technical Improvements

### Setup Script (`mac.sh`)
- ✅ Fixed unreachable bash function ordering (`subsequent_run()` moved before first call)
- ✅ Added comprehensive Python version detection loop (3.13, 3.12, 3.11, 3.10)
- ✅ Integrated Homebrew `python-tk` auto-installation for missing tkinter
- ✅ Implemented SDL2 dylib conflict resolution via symlink deduplication
- ✅ Enhanced error reporting with actionable user guidance

### Dependencies (`requirements.txt`)
- ✅ Fixed PyObjC package names (`pyobjc-framework-Cocoa` vs non-existent `AppKit`)
- ✅ Switched to `opencv-python-headless` to prevent SDL2 conflicts with pygame
- ✅ Verified all packages install cleanly on macOS arm64

### GUI Application (`shell_bookmark.py`)
- ✅ Added comprehensive Environment Variables settings tab
- ✅ Implemented file browser dialogs for intuitive path selection
- ✅ Added secure API key input with masking and visibility toggles
- ✅ Integrated version display in application title (`Radio OS v1.04`)
- ✅ Enhanced station launcher with environment variable support

## 🐛 Bug Fixes

### macOS Compatibility
- **SDL2 Warnings**: Resolved "Class X is implemented in both Y and Z" warnings
- **tkinter Import**: Fixed `ModuleNotFoundError: No module named '_tkinter'` on fresh installs
- **Package Dependencies**: Corrected non-existent PyObjC framework references
- **Setup Script Flow**: Fixed bash function ordering that prevented proper execution

### Cross-Platform Stability
- **Python Detection**: Robust version detection across different Python installations
- **Virtual Environment**: Improved radioenv activation and dependency management
- **Error Handling**: Better diagnostics for common setup and runtime issues

## 🎯 User Experience Improvements

### Simplified Configuration
- ❌ **Before**: Manual environment variable editing in terminal/config files
- ✅ **After**: Visual configuration panel with file browsers and validation

### Streamlined Setup
- ❌ **Before**: Manual dependency resolution and frequent setup failures
- ✅ **After**: Single-command setup with automatic conflict resolution

### Enhanced Security
- ❌ **Before**: Plain text API keys in config files
- ✅ **After**: Masked input fields with secure credential handling

## 📋 System Requirements

- **Python**: 3.10+ (auto-detected and installed if needed)
- **macOS**: 10.15+ with Homebrew (enhanced support)
- **Linux**: Modern distributions with tkinter support
- **Windows**: Windows 10/11 (existing support maintained)
- **Memory**: 2GB RAM minimum for audio processing
- **Storage**: 1GB for models and voice files

## 🚀 Getting Started

### Fresh Installation
```bash
git clone https://github.com/evengineer1ng/Radio-OS.git
cd Radio-OS
chmod +x mac.sh
./mac.sh
```

### Existing Users
1. Update your repository: `git pull origin main`
2. Run the desktop GUI: `python shell_bookmark.py`
3. Navigate to **Settings > Environment Variables** tab
4. Configure your preferred directories and API keys using the visual interface
5. Click **Launch Station** to test your configuration

### Environment Configuration
Access the new Environment Variables panel:
- **GUI**: Radio OS Shell → Settings → Environment Variables tab
- **Features**: File browsers, masked API key input, real-time validation
- **Supported Variables**: RADIO_OS_ROOT, RADIO_OS_PLUGINS, RADIO_OS_VOICES, API keys, and more

## 💡 What's New for Developers

### Environment Variable System
```python
# New global environment variable support
cfg = get_global_config()
env_vars = cfg.get("environment", {})

# Automatic station environment setup
env = setup_station_environment(station_manifest, global_cfg)
```

### Enhanced Station Launcher
```python
# Integrated with environment GUI
station_process = launch_with_environment(
    station_id="mystation",
    custom_env_vars=user_configured_vars
)
```

## 🔗 Integration Notes

This release maintains **100% backward compatibility** while adding powerful new configuration options. Existing stations, plugins, and configurations continue to work without modification.

The new environment variable system provides a seamless bridge between user configuration and runtime execution, making Radio OS significantly more accessible for new users while maintaining full flexibility for advanced users.

## 📚 Documentation Updates

- ✅ Enhanced README.md with v1.04 branding and environment variable documentation
- ✅ Added comprehensive setup troubleshooting guide
- ✅ Updated system requirements and dependency information
- ✅ Improved quick start guide with new GUI features

---

**Full Changelog**: [v1.03...v1.04](https://github.com/evengineer1ng/Radio-OS/compare/v1.03...v1.04)

**Download**: [Source code (zip)](https://github.com/evengineer1ng/Radio-OS/archive/refs/tags/v1.04.zip) | [Source code (tar.gz)](https://github.com/evengineer1ng/Radio-OS/archive/refs/tags/v1.04.tar.gz)