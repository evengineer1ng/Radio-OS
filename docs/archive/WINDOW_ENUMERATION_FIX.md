# Window Enumeration Issue & Fix - Visual Reader

## Problem
The visual reader's window dropdown shows **"(No windows found - try refreshing)"** even when multiple windows are open on the desktop.

## Root Cause
On Windows, the runtime is launched by `shell.py` with the `subprocess.CREATE_NO_WINDOW` flag. This flag creates the subprocess in a **detached/isolated mode** that prevents it from accessing the desktop window list via `win32gui.EnumWindows()`.

The issue occurs in:
- **shell.py line 383**: `kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW`
- **plugins/visual_reader.py line 625**: The `get_available_windows()` function calls `win32gui.EnumWindows()`, which fails silently because the subprocess is isolated from the desktop session.

## Solution

### 1. **Improved Error Handling in visual_reader.py**
Added better logging and a fallback mechanism when `EnumWindows()` fails:
- Logs when `EnumWindows()` returns empty (indicating subprocess isolation)
- Falls back to `tasklist.exe` enumeration (weaker, but better than nothing)
- Provides debugging information in the runtime log

### 2. **Make Console Visibility Conditional in shell.py**
Modified the launch logic to respect an environment variable:
```python
if not os.environ.get("RADIO_OS_SHOW_CONSOLE"):
    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
```

## How to Use

### Option A: Enable Console Window (Recommended for Window Enumeration)
When launching the shell, set the environment variable:

**PowerShell:**
```powershell
$env:RADIO_OS_SHOW_CONSOLE=1
python shell.py
```

**Command Prompt:**
```cmd
set RADIO_OS_SHOW_CONSOLE=1
python shell.py
```

This will:
- Show a console window for the runtime process
- Allow `win32gui.EnumWindows()` to properly enumerate desktop windows
- Enable better debugging/visibility

### Option B: Use Tasklist Fallback (No Change Required)
Leave the default behavior and the plugin will attempt to enumerate windows via `tasklist.exe` as a fallback. This is less reliable but works in some cases.

## Testing
1. Start the shell with `RADIO_OS_SHOW_CONSOLE=1`
2. Launch a station
3. Open the visual reader settings
4. Click "↻ (refresh)" next to the window dropdown
5. You should now see your open windows listed

## Technical Details

### Why This Happens
- `CREATE_NO_WINDOW` on Windows is designed to hide console output, typically for GUI applications
- However, it also isolates the subprocess from certain desktop resources
- `win32gui.EnumWindows()` requires the subprocess to have proper desktop access to enumerate windows
- The subprocess can still capture windows by exact title match via `win32gui.FindWindow()`, but enumeration doesn't work

### Why Tasklist Fallback is Weak
- `tasklist.exe` returns **process names**, not window titles
- A single application (e.g., Chrome) may have multiple windows with different titles
- This fallback helps in some cases but isn't reliable for the visual reader's use case

## Related Files
- [shell.py](shell.py#L375-L395) - Runtime launch logic
- [plugins/visual_reader.py](plugins/visual_reader.py#L607-L720) - Window enumeration code

## Future Improvements
1. **IPC-based window list**: Shell could communicate the window list to runtime via named pipes or sockets
2. **Enhanced COM-based enumeration**: Use Windows COM APIs (UIA) for more reliable window enumeration even in subprocess context
3. **Direct win32gui access from shell**: Enumerate windows in the shell process and pass results to the runtime
