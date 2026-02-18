# Manifest-Based Persistence - Theme & Layout Fix

## Overview
Fixed critical issues with theme and layout persistence by consolidating all configuration into the manifest instead of separate JSON files.

## Changes Made

### 1. **Theme Editor Bug Fixes** ✅
**Problem:** Colors were inconsistent - old values bled through, selections didn't stick deterministically.

**Root Cause:** 
- Multiple `make_media_row()` instances shared shallow copies of config dicts
- `make_color_row()` used `var.trace_add()` which fires on every keystroke, causing race conditions
- Different UI sections could overwrite each other's changes

**Fixes Applied:**
- `make_color_row()`: Changed from keystroke tracing to focus-out events
  - Only updates `set_fn()` when user leaves the field, not during typing
  - Prevents keystroke-level race conditions
  
- `make_media_row()`: Implemented proper deep copying via `copy.deepcopy()`
  - Each color/image/gradient/video switch gets a fresh, isolated config copy
  - Prevents reference contamination between sections
  - Ensures type changes (color→gradient) don't lose other config keys

### 2. **Layout & Theme Persistence** ✅

#### Before:
- Layout stored in separate `stations/<id>/ui_layout.json`
- User had to click "Load Layout" manually every startup
- Theme stored in manifest but layout was orphaned

#### After:
- **Layout now stored in manifest** under `CFG["ui_layout"]`
- **Auto-loads on startup** - no manual action needed
- **Backward compatible** - checks old JSON file if manifest entry missing
- Clean manifest-only approach for reproducibility

### 3. **Manifest as Source of Truth** ✅

**Layout Loading:**
```python
def _load_layout_file(self):
    # Try manifest first
    layout = CFG.get("ui_layout")
    if not layout:
        # Fallback to old JSON for compatibility
        # Read from _layout_path() (ui_layout.json)
    # Apply to panels
```

**Layout Saving:**
```python
def _save_layout_file(self):
    layout = {...serialize panels...}
    CFG["ui_layout"] = layout  # Into manifest
    save_station_manifest(CFG)  # Persist
```

**Auto-Load on Startup:**
- Added to `StationUI.__init__()` after `_install_builtin_widgets()`
- Calls `_load_layout_file()` automatically
- Then calls `apply_art()` to apply theme

### 4. **Plugin & Manifest Reproducibility** ✅

When a manifest is copied to another Radio OS installation:
- **Theme persists**: `CFG["art"]` contains all color/gradient/image configs
- **Layout persists**: `CFG["ui_layout"]` contains panel widget arrangement
- **No manual setup needed**: UI loads exactly as configured
- **Clean state**: No orphaned JSON files or stale caches

## Testing Checklist

- [ ] Open theme editor
- [ ] Change wallpaper to gradient, verify it shows
- [ ] Change wallpaper to image (GIF or PNG), verify it shows
- [ ] Change a panel to gradient, verify consistency
- [ ] Save theme, close station, reopen - verify theme persists
- [ ] Save layout (widgets in different panels), close, reopen - verify layout persists
- [ ] Copy manifest to another station folder - verify clean load

## Technical Details

### Config Structure (manifest.yaml)
```yaml
art:
  global_bg:
    type: "gradient"
    gradient:
      type: "linear"
      color1: "#121212"
      color2: "#4cc9f0"
  panels:
    left: {type: "color", value: "#121212"}
    center: {type: "color", value: "#121212"}
    right: {type: "color", value: "#121212"}
    toolbar: {type: "color", value: "#0e0e0e"}
    subtitle: {type: "color", value: "#0e0e0e"}
  accent: "#4cc9f0"
  subtitle_wave: true

ui_layout:
  panes:
    left:
      tabs: [{widget_key: "...", title: "..."}, ...]
    center:
      tabs: [{widget_key: "...", title: "..."}, ...]
    right:
      tabs: [{widget_key: "...", title: "..."}, ...]
```

### Race Condition Elimination

**Before:**
```python
var.trace_add("write", on_entry_change)  # Fires 120+ times per entry
```

**After:**
```python
ent.bind("<FocusOut>", on_focus_out)  # Fires once when done editing
```

### Deep Copy Pattern

**Before (Bug):**
```python
current_cfg = get_fn()  # Reference
cfg = current_cfg.copy()  # Shallow copy - nested dicts still reference
```

**After (Fixed):**
```python
import copy
initial_cfg = copy.deepcopy(get_fn())  # Full isolation
# Each refresh_media() does:
cfg = copy.deepcopy(get_fn())  # Fresh copy from backing store
```

## Migration Notes

- Old `ui_layout.json` files are **not deleted** (backward compat)
- Existing manifests **without `ui_layout`** will use defaults on first load
- Both theme and layout now persist across station reloads
- Manual "Load Layout" button now for browsing/applying saved layouts (future use)

## Files Modified

- `runtime.py`:
  - `make_color_row()` - Fixed keystroke race condition
  - `make_media_row()` - Added deep copy isolation
  - `_save_layout_file()` - Changed to save to manifest
  - `_load_layout_file()` - Changed to load from manifest with fallback
  - `StationUI.__init__()` - Added auto-load of layout and theme on startup
