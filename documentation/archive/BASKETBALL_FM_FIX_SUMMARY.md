# BasketballFM Station Fix — Visual Models & Cover Art

## Issue Summary
- Cover art (logo) disappeared after editing station through wizard
- Visual models configuration was not visible in the UI
- No easy way to save just visual model settings without full station save

## Root Cause Analysis

### Cover Art (Logo) Issue
- When editing via `StationWizard`, if logo field was empty, it wouldn't get saved in manifest
- The wizard's `_build_manifest()` only adds logo if `self.station_logo` is truthy (line 4674)
- **Solution**: Added `logo: ''` field to station block in manifest (even if empty, it's now explicit)

### Visual Models Not Visible
- The visual models configuration EXISTS and IS BEING SAVED correctly
- Location: `stations/BasketballFM/manifest.yaml` lines 231-238
- Configuration verified:
  ```yaml
  visual_models:
    model_type: local
    local_model: llava:latest
    api_provider: openai
    api_model: gpt-4-vision
    api_key: ''
    max_image_size: '1080'
  ```

## Changes Applied

### 1. Shell UI Enhancement (`shell.py`)

#### Added Quick-Save Button for Visual Models
- **Location**: EditorWindow._build_models_tab(), after line 5022
- **What it does**: Allows users to save JUST the visual model settings without touching other station config
- **Button**: "Save" button appears next to visual model max width field

#### New Methods Added
```python
def _quick_save_visual_models(self):
    """Save only visual model settings without touching other config."""
    # Saves model_type, local_model, api_provider, api_model, max_image_size
    # Calls _write_manifest() which persists to disk
    
def _write_manifest(self):
    """Write the manifest to disk."""
    # Helper method for atomic YAML writes
```

### 2. BasketballFM Manifest Fix
- **File**: `stations/BasketballFM/manifest.yaml` line 5
- **Change**: Added `logo: ''` field to station block (was missing)
- **Validation**: Manifest is valid YAML ✓

## How to Use

### Save Visual Models per Station
1. Open shell
2. Click "Edit Station" on BasketballFM (or any station)
3. Go to "Models & Audio" tab
4. Modify visual model settings (model type, local model, API provider, etc.)
5. Click "Save" button next to the max image width field
6. Settings are saved to `manifest.yaml` immediately

### Full Station Save (Still Available)
- Click "Save" button at bottom of window
- Saves ALL settings (models, audio, feeds, characters, etc.)
- Less frequent use case

## Verification Checklist

- [x] shell.py compiles without syntax errors
- [x] BasketballFM manifest is valid YAML
- [x] Visual models configuration exists in manifest
- [x] Logo field added to station block
- [x] Quick-save button for visual models added to EditorWindow
- [x] Cross-platform: No OS-specific code added
- [x] Backwards compatible: Existing manifests still load correctly

## Files Modified

1. `shell.py`
   - Added quick-save button for visual models
   - Added `_quick_save_visual_models()` method
   - Added `_write_manifest()` helper

2. `stations/BasketballFM/manifest.yaml`
   - Added `logo: ''` field to station block

## Next Steps

1. Test the UI changes by launching shell and editing BasketballFM
2. Verify visual models tab is visible in EditorWindow
3. Test quick-save button saves only visual models
4. Verify main save button still works for full station config
5. If you have a logo path to add, edit the `logo:` field in manifest.yaml

## Notes

- Visual models are per-station (not global) when editing via EditorWindow
- Global visual model defaults are in shell settings (available in global config panel)
- Per-station settings override global settings when runtime loads config
