# Theme Editor - Quick Test Guide

## Prerequisites
```bash
# Install new dependency
pip install Pillow>=9.0.0

# Or update all dependencies
pip install -r requirements.txt
```

## Step-by-Step Testing

### 1. Launch the Station
```bash
python shell.py
# Or launch a specific station via launcher.py
```

### 2. Open Theme Editor
- In the main window toolbar, find and click **"Theme Editor"** button
- A new window titled "Station Theme Editor" should open

### 3. Test Global Wallpaper Section

#### 3a. Test Color Mode
- Radio button should be on "Color"
- You should see a color picker with hex entry
- Click "Pick" button → native color chooser should open
- Change color and see the **swatch update live**

#### 3b. Test Image Mode
- Click "Image" radio button
- Button should change to "Browse..."
- Click "Browse..." → file dialog opens
- Select any PNG/JPG/GIF from your system
- Should see **image thumbnail preview** appear

#### 3c. Test Gradient Mode
- Click "Gradient" radio button
- Should see:
  - "Type" selector (Linear/Radial)
  - Two color pickers labeled "From" and "To"
  - Large **gradient preview canvas** showing live gradient
- Click color pickers and watch the preview update
- Try Linear vs. Radial gradients

#### 3d. Test Video Mode
- Click "Video" radio button
- Browse for an MP4 or GIF file
- Should show path in text field

### 4. Test Panel Customization

#### 4a. Each Panel (Left, Center, Right, Toolbar, Subtitle)
- Each should have type selector: Color / Gradient / Image
- Try different combinations:
  - Left panel: solid color
  - Center panel: gradient
  - Right panel: image
  - This demonstrates mix-and-match capability

#### 4b. For Image Panels
- Select Image mode
- Browse for an image
- Should see **thumbnail preview** of the image
- Click Browse again to change image

### 5. Test Accent Color
- Color picker similar to global background color mode
- Change accent color and see swatch update

### 6. Save & Apply
- After setting themes, click **"Save & Apply"** button
- Should see message: "Theme saved and applied!"
- Window closes
- Check that your themes are now applied:
  - Global background changed
  - Panels show their new backgrounds
  - Colors/gradients/images are visible

### 7. Verify Persistence
- Close and restart the station
- Theme should still be applied (saved in manifest)
- Open Theme Editor again → your settings should still be there

## Visual Checklist

### ✅ Should See:
- [ ] Large color swatches in editor (not tiny)
- [ ] Gradient preview canvas with smooth gradient visualization
- [ ] Image thumbnails showing preview of selected images
- [ ] Live updates as you change colors/options
- [ ] Clear section headers (🎨 Wallpaper, 🎴 Panels, ✨ Accent)
- [ ] Radio buttons for type selection
- [ ] "Pick" buttons for colors that open native color chooser

### ✅ Should Work:
- [ ] Color changes apply to swatches immediately
- [ ] Gradient preview updates when you change colors
- [ ] Image preview shows when you select an image
- [ ] Type selector switches UI appropriately
- [ ] Save & Apply button persists theme to manifest
- [ ] Background/wallpaper appears when applied
- [ ] Panels show their configured backgrounds

## Troubleshooting

### If images/gradients don't display:
1. Check PIL/Pillow is installed: `python -c "from PIL import Image; print('OK')"`
2. If not installed: `pip install Pillow`
3. Restart the station

### If colors show as "Pick" button not working:
1. Verify tkinter is installed properly
2. Try entering hex code manually (e.g., #FF0000)

### If gradients show but look wrong:
1. Verify PIL is installed
2. Try simpler colors first (e.g., #000000 to #FFFFFF)

### If persistent after Save & Apply:
1. Check manifest.yaml has "art" section:
   ```yaml
   art:
     global_bg:
       type: color
       value: "#..."
   ```
2. Try clicking "Reset Layout" button to force UI refresh

## Success Indicators

✨ **Full Success**: 
- You can set gradients and see them preview in the editor
- Images display as thumbnails in the editor
- After Save & Apply, wallpaper, panels, and gradients all appear on the main window
- Theme persists after restart

🎨 **Core Features Work**:
- Color selections work and update swatches
- All panel types can be configured independently
- Gradient preview canvas is functional
- Save/Apply doesn't error

## Questions?

See [THEME_EDITOR_CHANGES.md](THEME_EDITOR_CHANGES.md) for technical details on what was changed.
