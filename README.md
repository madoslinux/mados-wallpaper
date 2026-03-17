# madOS Wallpaper

A GTK3-based wallpaper manager for madOS that manages per-workspace wallpapers using SQLite.

## Features

- Manage wallpapers for 6 workspaces
- Reads/writes to SQLite database (`~/.local/share/mados/wallpapers.db`)
- Wallpapers are assigned randomly on first run
- Persists assignments across reboots
- Nord theme with consistent color palette

## Requirements

- Python 3.x
- GTK3 (`gir1.2-gtk-3.0`)
- GdkPixbuf (`gir1.2-gdkpixbuf-2.0`)
- sqlite3

## Installation

```bash
git clone https://github.com/madoslinux/mados-wallpaper.git
cd mados-wallpaper
```

## Running

```bash
python3 __main__.py
```

## Database

The app uses a SQLite database at `~/.local/share/mados/wallpapers.db`:

- **wallpapers**: id, path
- **assignments**: workspace (1-6), wallpaper_id

This is the same database used by `mados-sway-wallpapers` and `mados-wallpaper-glitch`.

## Configuration

Default wallpaper directories:
- `~/Imágenes`
- `~/Pictures`
- `/usr/share/backgrounds`
- `/usr/share/wayland-backgrounds`

## Architecture

### app.py - WallpaperApp

The main application class that:
- Creates and manages the GTK window
- Builds the wallpaper grid UI
- Handles user interactions (select workspace, assign wallpaper)

### config.py

Configuration constants:
- Colors (Nord palette)
- Database path
- Wallpaper directories
- Window dimensions