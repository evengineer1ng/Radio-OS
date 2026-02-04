# Theme Configuration Examples

These examples show the various theme configurations you can use in your `manifest.yaml`.

## Example 1: Dark Theme with Gradient

```yaml
art:
  global_bg:
    type: gradient
    value: "#0e0e0e"  # fallback color
    gradient:
      type: linear
      color1: "#0a0a0a"
      color2: "#1a1a1a"
  
  panels:
    left:
      type: color
      value: "#121212"
    center:
      type: color
      value: "#141414"
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

## Example 2: Wallpaper Image with Solid Panels

```yaml
art:
  global_bg:
    type: image
    value: "#0e0e0e"  # fallback if image not found
    path: "C:\\path\\to\\wallpaper.png"
  
  panels:
    left:
      type: color
      value: "#1a1a1a"
    center:
      type: color
      value: "#1a1a1a"
    right:
      type: color
      value: "#1a1a1a"
    toolbar:
      type: color
      value: "#0e0e0e"
    subtitle:
      type: color
      value: "#0e0e0e"
  
  accent: "#ff6b6b"  # red accent
```

## Example 3: Video Background with Gradient Panels

```yaml
art:
  global_bg:
    type: video
    value: "#0e0e0e"
    path: "C:\\path\\to\\background.mp4"
  
  panels:
    left:
      type: gradient
      gradient:
        type: linear
        color1: "#1a1a2e"
        color2: "#16213e"
    center:
      type: color
      value: "#0f3460"
    right:
      type: gradient
      gradient:
        type: radial
        color1: "#533483"
        color2: "#2a1647"
    toolbar:
      type: color
      value: "#0e0e0e"
    subtitle:
      type: color
      value: "#0e0e0e"
  
  accent: "#e94560"
```

## Example 4: Image-Based Panels

```yaml
art:
  global_bg:
    type: color
    value: "#000000"
  
  panels:
    left:
      type: image
      path: "C:\\path\\to\\panel_left.png"
    center:
      type: image
      path: "C:\\path\\to\\panel_center.png"
    right:
      type: image
      path: "C:\\path\\to\\panel_right.png"
    toolbar:
      type: color
      value: "#1a1a1a"
    subtitle:
      type: color
      value: "#1a1a1a"
  
  accent: "#00ff00"
```

## Example 5: Mixed Types with Radial Gradients

```yaml
art:
  global_bg:
    type: gradient
    value: "#000033"
    gradient:
      type: radial
      color1: "#1a1a4d"
      color2: "#0d0d26"
  
  panels:
    left:
      type: gradient
      gradient:
        type: linear
        color1: "#2a2a5a"
        color2: "#0a0a2a"
    center:
      type: color
      value: "#0f0f3f"
    right:
      type: gradient
      gradient:
        type: linear
        color1: "#2a2a5a"
        color2: "#0a0a2a"
    toolbar:
      type: color
      value: "#05051f"
    subtitle:
      type: gradient
      gradient:
        type: linear
        color1: "#1a1a4d"
        color2: "#000033"
  
  accent: "#00ccff"  # cyan
```

## Example 6: Neon Theme

```yaml
art:
  global_bg:
    type: color
    value: "#0a0e27"
  
  panels:
    left:
      type: gradient
      gradient:
        type: linear
        color1: "#0f1829"
        color2: "#1a0a29"
    center:
      type: gradient
      gradient:
        type: linear
        color1: "#1a0a29"
        color2: "#0f1829"
    right:
      type: gradient
      gradient:
        type: linear
        color1: "#1a2909"
        color2: "#0a0a19"
    toolbar:
      type: color
      value: "#05051f"
    subtitle:
      type: color
      value: "#0a0e27"
  
  accent: "#ff00ff"  # magenta
```

## Example 7: Nature-Inspired (Greens)

```yaml
art:
  global_bg:
    type: gradient
    value: "#1a3a1a"
    gradient:
      type: linear
      color1: "#0a2a0a"
      color2: "#1a4a2a"
  
  panels:
    left:
      type: color
      value: "#0f2a0f"
    center:
      type: color
      value: "#1a3a1a"
    right:
      type: color
      value: "#0f2a0f"
    toolbar:
      type: color
      value: "#0a1a0a"
    subtitle:
      type: color
      value: "#0a1a0a"
  
  accent: "#2ee59d"  # bright green
```

## Color Reference

### Common Colors Used:
- **Blacks/Grays**: `#000000`, `#0a0a0a`, `#121212`, `#1a1a1a`, `#2a2a2a`
- **Blues**: `#0f1829`, `#0f3460`, `#1a2a4a`, `#1a1a4d`
- **Purples**: `#1a0a29`, `#2a1647`, `#533483`
- **Greens**: `#0f2a0f`, `#1a3a1a`, `#2a4a2a`
- **Accents**: `#4cc9f0` (cyan), `#ff00ff` (magenta), `#00ff00` (green), `#ff6b6b` (red), `#2ee59d` (bright green)

## Tips for Creating Themes

1. **Contrast**: Make sure text is readable on your panel backgrounds
2. **Gradients**: Lighter to darker usually looks better than vice versa
3. **Images**: Use high-contrast images; subtle/blurred backgrounds work best
4. **Accent**: Choose a bright color that stands out from your background
5. **Consistency**: Keep panels in the same color family for professional look
6. **Testing**: Try the preview in the Theme Editor before applying

## How to Apply These Examples

1. Open your station's `manifest.yaml` file
2. Find the `art:` section (or create one if missing)
3. Copy one of the examples above
4. Update file paths if using images/videos
5. Save the manifest
6. Restart the station or use "Reset Layout" button

Alternatively, use the Theme Editor GUI to configure interactively and the changes will be saved automatically.

## Notes

- All file paths should use forward slashes `/` or doubled backslashes `\\` in YAML
- Colors must be valid hex codes: `#RRGGBB` or `#RRGGBBAA` (with alpha)
- For gradients, both `color1` and `color2` are required
- The `value` field serves as a fallback if image/video cannot be loaded
- If a panel config is missing, it defaults to `#121212` (dark gray)
