# Save System Debugging Enhancement

## Problem
User reports that manual saves (via "Save Game" button) are not creating files in the `saves/` directory. Save names are entered but files never appear.

## Diagnosis Approach
Added comprehensive debug logging to trace the save flow and identify where it's failing:

### 1. Widget Save Button (Line ~27386)
Added logging to see if:
- User enters a save name
- Path is correctly constructed  
- Command is sent to controller

**Changes:**
```python
def save_game(self):
    """Prompt for save name and save"""
    name = simpledialog.askstring("Save Game", "Enter save name:")
    if name:
        print(f"[WIDGET] User entered save name: {name}")
        # ... path construction ...
        print(f"[WIDGET] Sending save command with path: {path}")
        self.runtime["ftb_cmd_q"].put({"cmd": "ftb_save", "path": path})
    else:
        print("[WIDGET] Save cancelled - no name entered")
```

### 2. Controller save_game() Method (Line ~30618)
Added logging to verify:
- Method is called with correct path
- State exists (not None)
- Background thread is started

**Changes:**
```python
def save_game(self, path: Optional[str] = None) -> None:
    """Save current state to JSON in background thread (non-blocking)"""
    if not self.state:
        print("[SAVE] ❌ Cannot save - no state loaded")
        return
    
    if path is None:
        path = self._get_autosave_path()
    
    print(f"[SAVE] 💾 Initiating save to: {path}")
    # ... rest of method ...
```

### 3. Background Save Worker (Line ~30635)
Enhanced error handling with full traceback:
- Success confirmation with file path
- Detailed error messages with full traceback
- Separate error handling for notification failures

**Changes:**
```python
def _save_game_worker(self, path: str) -> None:
    """Background worker for saving game state"""
    try:
        # ... save logic ...
        print(f"[SAVE] ✅ Save complete: {path}")
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        self.log("ftb", f"[AUTOSAVE] Background save failed: {e}\n{error_details}")
        print(f"[SAVE] ❌ Save failed: {e}\n{error_details}")
        # ... error notification ...
```

## Expected Console Output

### Successful Save:
```
[WIDGET] User entered save name: trythis
[WIDGET] Sending save command with path: /path/to/Radio-OS-1.03/saves/trythis.json
[SAVE] 💾 Initiating save to: /path/to/Radio-OS-1.03/saves/trythis.json
[SAVE] ✅ Save complete: /path/to/Radio-OS-1.03/saves/trythis.json
```

### Failed Save (with details):
```
[WIDGET] User entered save name: trythis
[WIDGET] Sending save command with path: /path/to/Radio-OS-1.03/saves/trythis.json
[SAVE] 💾 Initiating save to: /path/to/Radio-OS-1.03/saves/trythis.json
[SAVE] ❌ Save failed: [error message]
Traceback (most recent call last):
  ... full error traceback ...
```

### Cancelled Save:
```
[WIDGET] Save cancelled - no name entered
```

## Next Steps for User

1. **Launch the game** and load your save
2. **Click "Save Game"** button
3. **Enter a save name** (e.g., "debug_test")
4. **Check the terminal/console** for the debug output
5. **Report what you see**:
   - Does `[WIDGET]` message appear?
   - Does `[SAVE]` message appear?
   - Are there any error messages?
   - What's the complete output?

## Possible Issues We're Looking For

### Issue 1: Command Not Reaching Controller
- Symptom: `[WIDGET]` message appears but no `[SAVE]` message
- Cause: Queue not connected or controller not processing commands
- Solution: Check ftb_cmd_q initialization

### Issue 2: State Not Loaded
- Symptom: `[SAVE] ❌ Cannot save - no state loaded`
- Cause: Controller's `self.state` is None
- Solution: Check state loading during game start

### Issue 3: Permission/Path Error
- Symptom: `[SAVE] ❌ Save failed:` with permission or file error
- Cause: Cannot write to saves directory
- Solution: Check file permissions or path resolution

### Issue 4: Serialization Error
- Symptom: Error in `save_to_json()` with object serialization
- Cause: Some game object can't be converted to JSON
- Solution: Fix serialization for that object type

## Files Modified
- `plugins/ftb_game.py`:
  - Line ~27386: Widget save_game() with debug output
  - Line ~30618: Controller save_game() with state check
  - Line ~30635: _save_game_worker() with full traceback

## Testing
After making these changes:
1. Restart the game
2. Load your save (championshiprun.json)
3. Try to save with a new name
4. Watch console for debug messages
5. Check if file appears in `saves/` directory

The debug output will tell us exactly where the save process is breaking down.
