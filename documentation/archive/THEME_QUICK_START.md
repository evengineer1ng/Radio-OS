# Theme Editor - Quick Start Guide

## TL;DR (30 seconds)

1. **Install Pillow:** `pip install Pillow`
2. **Launch station:** `python shell.py`
3. **Open Theme Editor:** Click "Theme Editor" button in toolbar
4. **Try it:** 
   - Select "Gradient" for global background
   - Pick two colors
   - See gradient preview live
   - Click "Save & Apply"
5. **Done!** Your theme is now active and saved

## What You Can Do Now

### Wallpapers
- **Colors:** Solid hex colors (#0e0e0e, #ff0000, etc.)
- **Gradients:** Smooth transitions (linear left→right, radial center→out)
- **Images:** PNG, JPG, GIF files with preview
- **Videos:** MP4, GIF animations

### Panels (5 of them)
- Left, Center, Right, Toolbar, Subtitle
- Each can be: color, gradient, or image
- All independent - mix and match!

### Mix & Match Examples
```
Example 1: Video wallpaper + solid color panels
Example 2: Gradient wallpaper + gradient panels  
Example 3: Image wallpaper + transparent panels
Example 4: Each panel a different gradient
```

## Opening the Theme Editor

### Method 1: GUI (Easiest)
1. Run the station: `python shell.py`
2. Look for "Theme Editor" button in toolbar
3. Click it → Theme Editor window opens

### Method 2: Command Line (For specific station)
```bash
python launcher.py  # Launches specific station
# Then use Theme Editor button as above
```

## Basic Workflow

### Step 1: Pick a Theme Type

**Global Wallpaper** section at top:
- Click radio button: Color / Image / Gradient / Video

### Step 2: Configure Your Choice

**For Color:**
- Click "Pick" button → color chooser opens
- Select color
- See swatch update

**For Gradient:**
- Choose type: Linear or Radial
- Click "Pick" for Color 1 (start color)
- Click "Pick" for Color 2 (end color)
- Watch gradient preview update live!

**For Image:**
- Click "Browse" button
- Select PNG, JPG, or GIF file
- See thumbnail preview appear

**For Video:**
- Click "Browse" button
- Select MP4 or GIF file

### Step 3: Customize Panels (Optional)

Scroll down to "Panel Customization" section:
- Each panel can be: Color / Gradient / Image
- Configure each one independently
- Watch preview of each

### Step 4: Set Accent Color

- Optional but recommended
- Used for highlights, buttons, focus
- Click "Pick" to choose

### Step 5: Save & Apply

- Click "Save & Apply" button at bottom
- Theme applies immediately
- Saved to your manifest

## Visual Tips

### What to Look For

**Large Color Swatches:**
- Before: Tiny 4-character wide boxes
- Now: 8-character wide, 2-character tall → much more visible!

**Gradient Preview:**
- New: Live canvas showing your gradient
- Updates in real-time as you pick colors
- Shows smooth transition from color1 to color2

**Image Preview:**
- New: Thumbnail of your selected image
- Lets you confirm it looks right before applying

## Common Tasks

### Create a Neon Cyberpunk Theme
1. Global: Gradient, Linear, #1a1a4d → #000033
2. Left Panel: Gradient, Radial, #2a2a5a → #0a0a2a
3. Center Panel: Color, #0f0f3f
4. Right Panel: Gradient, Linear, #2a2a5a → #0a0a2a
5. Accent: #ff00ff (magenta)
6. Save & Apply

### Use Your Desktop Wallpaper
1. Global: Image
2. Click Browse
3. Navigate to your wallpaper
4. Click "Save & Apply"

### Create Gradient Panels
1. Scroll to Panel Customization
2. Each panel → Gradient mode
3. Mix linear and radial types
4. Different colors for each
5. Save & Apply

## Troubleshooting

### "Gradient mode not working"
→ Make sure Pillow is installed: `pip install Pillow`

### "Image preview not showing"
→ File might not exist or wrong format. Try:
- PNG or JPG only (GIF sometimes finicky)
- Different image file
- Check file path is correct

### "Theme not applying"
→ Try "Reset Layout" button in main window toolbar
→ Restart the station
→ Check manifest.yaml has art config

### "My theme disappeared after restart"
→ Theme is saved! Check it reappeared
→ If not, theme might not have saved - try Save & Apply again

## Performance

- No lag or stuttering from themes
- Gradients are fast (rendered once)
- Images are cached (loaded once)
- Works on all platforms (Windows, Mac, Linux)

## Next Steps

1. **Try It:** Open Theme Editor and play with gradients
2. **Explore:** Look at [THEME_EXAMPLES.md](THEME_EXAMPLES.md) for inspiration
3. **Learn:** See [MANIFEST_ART_REFERENCE.md](MANIFEST_ART_REFERENCE.md) for all options
4. **Test:** Follow [THEME_EDITOR_TESTING.md](THEME_EDITOR_TESTING.md) for thorough testing

## Pro Tips

- **Live Preview:** Changes preview in editor before you click Save & Apply
- **Type Selector:** Radio buttons let you switch types without losing config
- **Fallback Color:** Always set a fallback color (used if image/video fails)
- **Hex Input:** You can type hex codes directly if you know them
- **Reset:** Click "Reset Layout" to see major changes take effect

## Common Hex Colors (Copy-Paste Ready)

```
Black:       #000000
White:       #ffffff
Dark Gray:   #0e0e0e
Light Gray:  #e8e8e8
Red:         #ff0000
Green:       #00ff00
Blue:        #0000ff
Cyan:        #00ffff
Magenta:     #ff00ff
Yellow:      #ffff00
Orange:      #ff8800
Purple:      #8800ff
```

## Files Reference

- **Quick Answers:** This file (you're reading it!)
- **Working Examples:** [THEME_EXAMPLES.md](THEME_EXAMPLES.md)
- **Complete Reference:** [MANIFEST_ART_REFERENCE.md](MANIFEST_ART_REFERENCE.md)
- **Technical Details:** [THEME_EDITOR_CHANGES.md](THEME_EDITOR_CHANGES.md)
- **Testing Guide:** [THEME_EDITOR_TESTING.md](THEME_EDITOR_TESTING.md)

---

**Ready?** Open Theme Editor and create something beautiful! 🎨
