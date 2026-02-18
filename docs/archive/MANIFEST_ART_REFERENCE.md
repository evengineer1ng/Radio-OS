# Manifest.yaml - Art Configuration Reference

This file shows the complete structure of the `art` configuration in your station's `manifest.yaml`.

## Complete Structure

```yaml
# Station Configuration Manifest

# ... other station config ...

art:
  # GLOBAL BACKGROUND (Wallpaper)
  global_bg:
    type: color              # One of: color, image, gradient, video
    value: "#0e0e0e"        # Fallback color (used if image/video fails)
    
    # If type is "image" or "video":
    path: "path/to/file.png" # Path to PNG, JPG, GIF (image) or MP4, GIF (video)
    
    # If type is "gradient":
    gradient:
      type: linear           # One of: linear, radial
      color1: "#0a0a0a"      # Start color
      color2: "#1a1a1a"      # End color

  # PANEL BACKGROUNDS
  panels:
    left:
      type: color            # One of: color, image, gradient
      value: "#121212"       # Used for type: color
      path: "path/to/image.png"  # Used for type: image
      gradient:              # Used for type: gradient
        type: linear         # One of: linear, radial
        color1: "#121212"
        color2: "#1a1a1a"
    
    center:
      type: color
      value: "#121212"
    
    right:
      type: color
      value: "#121212"
    
    toolbar:
      type: color
      value: "#0e0e0e"
    
    subtitle:
      type: color
      value: "#0e0e0e"

  # ACCENT COLOR
  accent: "#4cc9f0"  # Used for highlights, focus indicators, text emphasis

  # OPTIONAL
  subtitle_wave: true        # Show waveform in subtitle (boolean)
```

## Minimal Example

At minimum, you only need:

```yaml
art:
  global_bg:
    type: color
    value: "#0e0e0e"
  panels:
    left:
      type: color
      value: "#121212"
    center:
      type: color
      value: "#121212"
    right:
      type: color
      value: "#121212"
    toolbar:
      type: color
      value: "#0e0e0e"
    subtitle:
      type: color
      value: "#0e0e0e"
  accent: "#4cc9f0"
```

## Type Specifications

### type: "color"
Solid color background.
```yaml
global_bg:
  type: color
  value: "#0e0e0e"      # Hex color code, required
```

### type: "image"
Image file (PNG, JPG, GIF).
```yaml
global_bg:
  type: image
  value: "#0e0e0e"      # Fallback if image not found (required)
  path: "/absolute/path/to/image.png"  # Full path, required
```

### type: "gradient"
Linear or radial color gradient.
```yaml
global_bg:
  type: gradient
  value: "#0e0e0e"      # Fallback color (required)
  gradient:
    type: linear        # or "radial" (required)
    color1: "#0a0a0a"   # Start/center color (required)
    color2: "#1a1a1a"   # End/outer color (required)
```

### type: "video"
Video file (MP4, GIF animations).
```yaml
global_bg:
  type: video
  value: "#0e0e0e"      # Fallback if video can't play (required)
  path: "/absolute/path/to/video.mp4"  # Full path, required
```

## Field Reference

| Field | Type | Where Used | Required | Notes |
|-------|------|-----------|----------|-------|
| type | string | All | Yes | color, image, gradient, video |
| value | string | All | Yes | Hex color as fallback |
| path | string | image, video | If type is image/video | Full absolute path |
| gradient | object | Global/panels | If type is gradient | Contains type, color1, color2 |
| gradient.type | string | Gradient | Yes | "linear" or "radial" |
| gradient.color1 | string | Gradient | Yes | Hex color code |
| gradient.color2 | string | Gradient | Yes | Hex color code |
| accent | string | Root level | Yes | Hex color for UI highlights |

## Path Guidelines

### Absolute vs Relative
- Always use **absolute paths** in manifest for reliability
- Relative paths may fail depending on working directory

### Examples
```
Windows:
  path: "C:\\Users\\Username\\Pictures\\wallpaper.png"
  path: "D:\\Media\\background.mp4"

Linux/Mac:
  path: "/home/username/pictures/wallpaper.png"
  path: "/Users/username/wallpaper.png"
```

### Finding Absolute Path
- Windows: Right-click file → Properties → Full path
- Mac: Right-click → Get info → Full path  
- Linux: `realpath /path/to/file`

## Color Format

### Hex Colors
- Format: `#RRGGBB` (e.g., `#ff0000` is red)
- Case insensitive: `#FF0000` or `#ff0000` both work
- Transparency: `#RRGGBBAA` (e.g., `#ff000080` is semi-transparent red)

### Common Colors
```yaml
Black:       "#000000"
White:       "#ffffff"
Dark Gray:   "#0e0e0e"
Light Gray:  "#e8e8e8"
Red:         "#ff0000"
Green:       "#00ff00"
Blue:        "#0000ff"
Cyan:        "#00ffff"
Magenta:     "#ff00ff"
Yellow:      "#ffff00"
```

## Gradient Type Comparison

### Linear Gradient
- Direction: Left to right
- Start: color1 on left
- End: color2 on right
- Best for: Horizontal backgrounds, wide panels

```yaml
gradient:
  type: linear
  color1: "#000000"
  color2: "#ffffff"
```
Result: Black on left fading to white on right

### Radial Gradient
- Direction: Center to edges
- Center: color1 in middle
- Edge: color2 at edges
- Best for: Spotlight effects, circular panels

```yaml
gradient:
  type: radial
  color1: "#ffffff"
  color2: "#000000"
```
Result: White in center fading to black at edges

## Error Handling

If any value is invalid or file not found:
1. Image/video path doesn't exist → uses `value` fallback color
2. Invalid hex color → uses default (#121212)
3. Missing panel → uses default (#121212)
4. Missing accent → uses default (#4cc9f0)

The system is robust and won't crash on invalid config.

## Examples by Use Case

### Simple Dark Theme
```yaml
art:
  global_bg:
    type: color
    value: "#0e0e0e"
  panels:
    left: {type: color, value: "#121212"}
    center: {type: color, value: "#121212"}
    right: {type: color, value: "#121212"}
    toolbar: {type: color, value: "#0e0e0e"}
    subtitle: {type: color, value: "#0e0e0e"}
  accent: "#4cc9f0"
```

### Gradient Theme
```yaml
art:
  global_bg:
    type: gradient
    value: "#0e0e0e"
    gradient:
      type: linear
      color1: "#0a0a0a"
      color2: "#1a1a1a"
  panels:
    left: {type: color, value: "#121212"}
    center: {type: gradient, gradient: {type: linear, color1: "#1a1a2e", color2: "#16213e"}}
    right: {type: color, value: "#121212"}
    toolbar: {type: color, value: "#0e0e0e"}
    subtitle: {type: color, value: "#0e0e0e"}
  accent: "#ff00ff"
```

### Image Wallpaper
```yaml
art:
  global_bg:
    type: image
    value: "#000000"
    path: "/path/to/wallpaper.png"
  panels:
    left: {type: color, value: "#1a1a1a"}
    center: {type: color, value: "#1a1a1a"}
    right: {type: color, value: "#1a1a1a"}
    toolbar: {type: color, value: "#0e0e0e"}
    subtitle: {type: color, value: "#0e0e0e"}
  accent: "#00ff00"
```

## Validation Checklist

Before saving your manifest:

- [ ] All color values are valid hex (#RRGGBB or #RRGGBBAA)
- [ ] Image/video paths are absolute and file exists
- [ ] Types are one of: color, image, gradient, video
- [ ] Gradient types are: linear or radial
- [ ] All panels have a configuration
- [ ] Fallback value exists for every panel/background
- [ ] YAML syntax is valid (proper indentation)

## Testing Your Config

1. Edit manifest.yaml with your art config
2. Save the file
3. Restart the station
4. Theme should apply automatically
5. Or use Theme Editor GUI to verify

## Tips & Tricks

### Fast Color Tweaking
Edit manifest.yaml directly and restart rather than using GUI repeatedly.

### Testing Gradients
- Try `color1: "#0a0a0a"` and `color2: "#1a1a1a"` for subtle dark gradients
- Try `color1: "#1a1a2e"` and `color2: "#16213e"` for blue tint
- Try `color1: "#2a1647"` and `color2: "#1a0a29"` for purple tint

### Image Tips
- Use high-contrast images for best visibility
- Blur/fade images so text is readable
- Resize large images (1920x1080 or smaller)
- Test both PNG and JPG for quality/size tradeoff

### Backup Your Theme
Keep a copy of your art config section before major changes.

---

For interactive editing, use the Theme Editor GUI (Theme Editor button in toolbar).
For reference, see [THEME_EXAMPLES.md](THEME_EXAMPLES.md) for complete working examples.
