# Radio OS Changelog

## Version 1.06 (February 13, 2026)

### � FTB - Phase 2 Historical Data Integration

**Complete Historical Tracking System**
- Automatic updates after every race (streaks, momentum, pulse)
- Season-end bulk updates for career totals and prestige
- Historical context automatically injected into narrator prompts
- Rich storytelling with actual game history instead of hallucinations

**Live Race Viewing**
- Real-time race event display with 2-second lap-by-lap intervals
- Interactive dialog to watch live or skip to instant results
- Smart triggering only for single tick advances
- Enhanced ftb_pbp widget for live race display

**New Database Schema**
- `historical_streaks`: Win/loss/podium streak tracking
- `historical_momentum`: Performance trends and pulse metrics
- `historical_career`: Lifetime totals (races, wins, championships)
- `historical_achievements`: Milestone tracking
- `historical_prestige`: Team reputation and peak performance
- Championship records table

**New Tools & Plugins**
- `ftb_historical_integration.py`: Core historical data management
- `ftb_data_explorer.py`: Query and analyze historical data
- `ftb_db_explorer.py`: Database inspection utilities
- `ftb_remote.py`: Remote game state access
- `tools/ftb_historical_data_bootstrap.py`: Bootstrap existing saves

**Narrator Enhancements**
- Historical context injection in prompts
- Streak and momentum awareness
- Achievement and milestone callouts
- Career statistics references

**Web Interface**
- New FTBData.svelte tab for historical visualization
- Enhanced App.svelte navigation
- WebSocket integration for real-time updates

### �🍎 macOS-Focused Improvements

**Enhanced Flows Media Player Integration**
- Robust AppleScript backend with proper error handling
- Music.app and Spotify support with timeout protection
- FileNotFoundError catching for missing osascript
- Improved control commands with validation and logging
- Better state tracking and playback detection

**Fixed UI Button Colors on Mac**
- Toolbar buttons now display proper themed colors on macOS
- Platform-specific button implementation (Label on Mac, Button on Windows/Linux)
- All themed buttons (purple, green, red, blue, teal, magenta) render correctly
- Maintained hover effects and interactions

**Card Loading Fix**
- Fixed station cards not appearing after exiting a station on macOS
- Smart geometry updates with platform-specific `update_idletasks()` calls
- New `_force_card_refresh()` method for reliable Mac transitions
- Improved carousel positioning and snapping

**Reduced Widget Window Borders**
- Removed excessive border padding on widget windows for Mac
- Zero-border design (`bd=0`, `highlightthickness=0`) on macOS
- Cleaner appearance with more usable screen space
- Better alignment with macOS design standards

**Button Text Improvements**
- Changed harsh white (`#ffffff`) to softer `#e8e8e8` for better contrast
- Reduced eye strain on dark backgrounds
- Applied to theme editor, media editor, prompt editor, and queue buttons

### 🔧 Technical Changes

- Enhanced `MacAppleScriptBackend` error handling in `plugins/flows.py`
- Platform-specific button creation in `bookmark.py` toolbar
- Mac-specific geometry updates in `shell_bookmark.py` card rendering
- Conditional border styling for `FloatingWindow` class

### 📁 Files Changed
- `plugins/flows.py`: Mac media backend improvements
- `bookmark.py`: Button colors, widget borders, text contrast
- `shell_bookmark.py`: Card loading fix, version bump to 1.06

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