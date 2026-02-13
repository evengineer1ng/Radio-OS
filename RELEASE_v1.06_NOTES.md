# Radio OS v1.06 - macOS UI & FTB Historical Data Integration

## 🍎 macOS-Focused Improvements

Radio OS v1.06 delivers significant enhancements to the macOS experience, fixing UI rendering issues, improving media player integration, and ensuring buttons and widgets display correctly on Mac.

## 🏁 From The Backmarker (FTB) - Phase 2 Historical Data Integration

**Major Update:** Complete historical data tracking system with automatic game loop integration!

### Historical Data System (Phase 2)
- **Automatic Updates**: Streaks, momentum, and pulse calculated after every race
- **Career Tracking**: Season-end bulk updates for career totals, prestige, peak performance
- **Narrator Context**: Historical data automatically injected into narrator prompts
- **Rich Storytelling**: Narrator can reference actual game history instead of hallucinating
- **Performance Metrics**: Win/loss streaks, championship records, milestone achievements
- **Team Pulse System**: 0-100 metric tracking recent performance momentum

### Live Race Viewing
- **Real-time Race Events**: Watch races unfold lap-by-lap with 2-second intervals
- **Interactive Choice**: Dialog prompt to watch live or skip to instant results
- **Smart Triggering**: Only for single tick advances (batches run instantly)
- **Delegate Compatible**: No interruptions in delegate/auto mode
- **Position Updates**: See overtakes, crashes, and position changes live
- **ftb_pbp Widget**: Enhanced play-by-play display for live races

### New FTB Tools & Plugins
- **`ftb_historical_integration.py`**: Core historical data management
- **`ftb_data_explorer.py`**: Query and analyze historical game data
- **`ftb_db_explorer.py`**: Database inspection utilities
- **`ftb_remote.py`**: Remote game state access
- **Bootstrap Tool**: `tools/ftb_historical_data_bootstrap.py` for existing saves

### Enhanced Database Schema
- **`historical_streaks`**: Track win/loss/podium streaks per team
- **`historical_momentum`**: Recent performance trends and pulse metrics
- **`historical_career`**: Lifetime totals (races, wins, championships)
- **`historical_achievements`**: Milestone tracking (first win, 100th race, etc.)
- **`historical_prestige`**: Team reputation and peak performance
- **Championship Records**: Season-by-season championship history

### Narrator Enhancements
- **Historical Context Injection**: Auto-enrichment with team history
- **Streak Recognition**: "on a 5-race win streak" references
- **Momentum Awareness**: High/low pulse period recognition
- **Achievement Callouts**: Milestone and record-breaking moments
- **Career Statistics**: Reference to lifetime performance

### Web Interface Improvements
- **FTBData.svelte**: New web tab for historical data visualization
- **Enhanced App.svelte**: Better navigation and state management
- **WebSocket Integration**: Real-time data updates via debug server

## ✨ macOS UI & Media Features

### Enhanced Flows Media Player Integration (macOS)
- **Robust AppleScript Backend**: Improved Mac media player integration with proper error handling
- **Music.app & Spotify Support**: Seamless integration with both Music.app and Spotify
- **Better Error Recovery**: 
  - Timeout handling for AppleScript commands
  - FileNotFoundError catching for missing osascript
  - Detailed logging for debugging media issues
- **Improved Control Commands**: Enhanced play/pause/skip controls with validation
- **State Tracking**: More reliable playback state detection and updates

### Fixed UI Button Colors on Mac
- **Proper Color Display**: Toolbar buttons now show their intended colors on macOS
- **Platform-Specific Implementation**: 
  - Mac uses `tk.Label` with click bindings (full color support)
  - Windows/Linux continues using native `tk.Button`
- **All Themed Buttons Work**: Purple, green, red, blue, teal, magenta buttons now render correctly
- **Hover Effects**: Smooth color transitions on mouse hover maintained

### Card Loading Fix (shell_bookmark.py)
- **Reliable Card Rendering**: Fixed issue where station cards wouldn't load after exiting a station
- **Smart Geometry Updates**: Platform-specific `update_idletasks()` calls ensure proper layout
- **Forced Refresh**: New `_force_card_refresh()` method for Mac transitions
- **Smooth Navigation**: Cards always appear correctly when returning to station browser

### Reduced Widget Window Borders
- **Cleaner Appearance**: Removed excessive border padding on widget windows for Mac
- **Zero-Border Design**: `bd=0` and `highlightthickness=0` on macOS
- **More Screen Space**: Less wasted space around widget edges
- **Native Look**: Better alignment with macOS design standards

### Button Text Improvements
- **Better Contrast**: Changed button text from harsh white (`#ffffff`) to softer `#e8e8e8`
- **Reduced Eye Strain**: More comfortable reading on dark backgrounds
- **Affected Buttons**:
  - Theme editor "Pick" buttons
  - Media editor "Clear" buttons
  - Prompt editor "Save" and "Reset" buttons
  - Producer queue "Flush" button

## 🔧 Technical Improvements

### Flows Plugin Enhancements (`plugins/flows.py`)
```python
# Improved error handling in MacAppleScriptBackend
- try-except blocks for all osascript calls
- Timeout handling (2 second limit)
- Graceful degradation when apps unavailable
- Detailed error logging for debugging
```

### Bookmark UI Updates (`bookmark.py`)
```python
# Platform-specific button creation
if IS_MAC:
    # Use Label with click bindings (full color support)
    btn = tk.Label(...)
else:
    # Use native Button (Windows/Linux)
    btn = tk.Button(...)
```

### Shell Enhancements (`shell_bookmark.py`)
```python
# Mac-specific geometry updates
if sys.platform == "darwin":
    self.root.update_idletasks()
    self.canvas.update_idletasks()
```

## 📋 Changed Files

**FTB System:**
- **`plugins/ftb_game.py`**: Race/season hooks for historical updates (+1,756 lines)
- **`plugins/ftb_narrative_prompts.py`**: Historical context enrichment (+122 lines)
- **`plugins/ftb_state_db.py`**: Enhanced database schema (+927 lines)
- **`plugins/ftb_web_server.py`**: WebSocket improvements (+207 lines)
- **New plugins**: ftb_historical_integration, ftb_data_explorer, ftb_db_explorer, ftb_remote
- **New tools**: ftb_historical_data_bootstrap.py
- **Web UI**: App.svelte, FTBData.svelte
- **Documentation**: FTB_PHASE2_QUICKSTART.md, PHASE2_EXECUTION_SUMMARY.md, LIVE_RACE_TESTING.md, and more

**macOS Improvements:**
- **`plugins/flows.py`**: Enhanced Mac media player backend with error handling
- **`bookmark.py`**: 
  - Fixed toolbar button colors on Mac
  - Reduced widget window borders on Mac
  - Improved button text contrast
- **`shell_bookmark.py`**: Fixed card loading after station exit

## 🚀 Upgrade Instructions

### From v1.05 or Earlier
```bash
# Pull latest changes
git pull origin main

# No dependencies changed - just restart Radio OS
python shell_bookmark.py
```

### First Time Setup
```bash
# Clone repository
git clone https://github.com/evengineer1ng/Radio-OS.git
cd Radio-OS

# Run setup
python setup.py

# Launch
python shell_bookmark.py
```

## 🐛 Bug Fixes

1. **Mac Media Integration Crashes**: Fixed crashes when Music.app or Spotify wasn't running
2. **Toolbar Button Colors**: Buttons now display with proper themed colors on macOS
3. **Card Loading**: Station cards reliably appear after exiting a running station
4. **Widget Window Borders**: Removed excessive border padding on Mac
5. **Button Text Readability**: Softer white color reduces eye strain

## 📚 Platform Compatibility

### Tested On
- ✅ **macOS 12+ (Monterey, Ventura, Sonoma)**: All features working
- ✅ **Windows 10/11**: Existing functionality maintained
- ✅ **Linux (Ubuntu 22.04+)**: Existing functionality maintained

### macOS-Specific Features
- Native AppleScript media integration
- Music.app and Spotify control
- Optimized UI rendering and geometry
- Platform-aware button styling
- Reduced border padding

## 🔮 Looking Ahead

Future releases will continue improving cross-platform compatibility:
- Linux media integration (MPRIS support)
- Additional voice provider options
- Enhanced plugin discovery
- Performance optimizations

## 💬 Feedback

Report issues or request features:
- GitHub Issues: https://github.com/evengineer1ng/Radio-OS/issues
- Discussions: https://github.com/evengineer1ng/Radio-OS/discussions

---

**Full Changelog**: https://github.com/evengineer1ng/Radio-OS/compare/v1.05...v1.06
