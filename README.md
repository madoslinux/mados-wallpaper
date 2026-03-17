# madOS Wallpaper

A lightweight GTK3-based wallpaper manager for Wayland compositors (Sway/Hyprland).

## Features

- Browse wallpapers from standard directories
- Preview wallpapers with thumbnails
- Set wallpaper with one click
- Detects Sway or Hyprland compositor automatically
- Nord theme with consistent color palette

## Requirements

- Python 3.x
- GTK3 (`gir1.2-gtk-3.0`)
- GdkPixbuf (`gir1.2-gdkpixbuf-2.0`)
- Sway or Hyprland compositor

## Installation

```bash
git clone https://github.com/madoslinux/mados-wallpaper.git
cd mados-wallpaper
```

## Running

```bash
python3 -m mados_wallpaper
```

## Usage

1. The application scans standard directories for images (`~/Imágenes`, `~/Pictures`, `/usr/share/backgrounds`)
2. Click on a wallpaper to select it
3. Click "Apply Wallpaper" to set it

## Architecture

### app.py - WallpaperApp

The main application class that:
- Creates and manages the GTK window
- Builds the wallpaper grid UI
- Handles user interactions

### wallpaper_scanner.py

Handles wallpaper scanning and compositor integration:
- `scan_wallpaper_dirs()` - Scans directories for image files
- `set_sway_wallpaper()` - Sets wallpaper on Sway
- `set_hyprland_wallpaper()` - Sets wallpaper on Hyprland
- `detect_compositor()` - Detects the running compositor

### config.py

Configuration constants:
- Colors (Nord palette)
- Default wallpaper directories
- Window dimensions

## Configuration

Wallpaper directories can be customized via environment variable:

```bash
WALLPAPER_DIRS="/path/to/wallpapers:/another/path" python3 -m mados_wallpaper
```

## State Persistence

State is saved to `~/.config/mados-wallpaper/state.json`:
- Last selected wallpaper
- Detected compositor