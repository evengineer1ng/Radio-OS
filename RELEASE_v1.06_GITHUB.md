# Radio OS v1.06 - macOS UI & FTB Historical Data Integration 🍎🏁

## 🌟 Highlights

This release combines macOS UI improvements with a major FTB update featuring complete historical data tracking, live race viewing, and enhanced narrator storytelling.

## ✨ What's New

### 🏁 FTB - Phase 2 Historical Data Integration

**Complete Historical Tracking System:**
- ✅ **Automatic Updates** after every race (streaks, momentum, pulse)
- ✅ **Career Tracking** with season-end bulk updates
- ✅ **Narrator Integration** with real game history context
- ✅ **Rich Storytelling** grounded in actual performance data

**Live Race Viewing:**
- 🔴 Watch races unfold **lap-by-lap** in real-time (2-second intervals)
- 🎮 **Interactive choice** to watch live or skip to instant results
- 📊 See overtakes, crashes, and position changes as they happen
- 🎯 Smart triggering (only single ticks, not batches)

**New Features:**
- Historical database schema (streaks, momentum, career, achievements, prestige)
- 4 new plugins (historical_integration, data_explorer, db_explorer, remote)
- Bootstrap tool for existing saves
- Enhanced narrator with historical context
- New FTBData web tab for visualization

### 🍎 macOS UI & Media
- **Robust AppleScript backend** with proper error handling for Music.app and Spotify
- **Timeout protection** prevents hanging when apps don't respond
- **Better error recovery** with detailed logging for debugging
- **Improved state tracking** for reliable playback detection

### 🎨 Fixed Toolbar Button Colors on Mac
- Buttons now display with their **proper themed colors** (purple, green, red, blue, teal, magenta)
- Platform-specific implementation ensures **full color support** on macOS
- Maintained smooth **hover effects** and interactions

### 🗂️ Fixed Card Loading Issue
- Station cards now **reliably appear** after exiting a running station
- Smart geometry updates with platform-specific rendering
- Smooth transitions back to station browser

### 🪟 Cleaner Widget Windows
- **Removed excessive border padding** on widget windows for Mac
- More usable screen space with zero-border design
- Better alignment with macOS design aesthetics

### 👁️ Improved Button Readability
- Changed harsh white text to **softer #e8e8e8** for better contrast
- Reduced eye strain on dark backgrounds
- Applied to all dialog and editor buttons

## 🔧 Technical Details

**FTB Changes (+3,012 lines):**
- `plugins/ftb_game.py` - Race/season hooks (+1,756)
- `plugins/ftb_narrative_prompts.py` - Historical enrichment (+122)
- `plugins/ftb_state_db.py` - Enhanced schema (+927)
- `plugins/ftb_web_server.py` - WebSocket improvements (+207)
- New plugins, tools, and web components

**macOS Improvements:**
- `plugins/flows.py` - Enhanced Mac media backend
- `bookmark.py` - Button colors, widget borders, text contrast
- `shell_bookmark.py` - Card loading fix, version bump

**Platform Support:**
- ✅ macOS 12+ (Monterey, Ventura, Sonoma)
- ✅ Windows 10/11
- ✅ Linux (Ubuntu 22.04+)

## 📦 Installation

### Upgrade from v1.05
```bash
git pull origin main
python shell_bookmark.py
```

### Fresh Install
```bash
git clone https://github.com/evengineer1ng/Radio-OS.git
cd Radio-OS
python setup.py
python shell_bookmark.py
```

## 🐛 Bug Fixes
- Mac media integration crashes when apps unavailable
- Toolbar buttons showing default colors instead of themed colors
- Station cards not appearing after station exit
- Excessive widget window borders on Mac
- Button text too bright on dark backgrounds

## 📝 Full Release Notes

See [RELEASE_v1.06_NOTES.md](RELEASE_v1.06_NOTES.md) for complete details.

---

**Full Changelog**: https://github.com/evengineer1ng/Radio-OS/compare/v1.05...v1.06
