# AGENTS.md - madOS Wallpaper Development Guide

## Project Overview

madOS Wallpaper is a GTK3-based wallpaper manager for Wayland compositors (Sway/Hyprland). It provides a simple interface to browse and set wallpapers.

## Build, Lint, and Test Commands

### Running the Application

```bash
# Run directly with Python
python3 -m mados_wallpaper
```

### Dependencies

The project requires:
- Python 3.x
- GTK3 (gir1.2-gtk-3.0)
- GdkPixbuf (gir1.2-gdkpixbuf-2.0)
- Sway or Hyprland compositor

### Testing

No test framework is currently configured.

### Linting

No linting tools are configured.

## Code Style Guidelines

### General Philosophy

- Keep code simple and readable
- Avoid premature abstraction
- Use explicit over implicit
- No comments unless they explain "why", not "what"

### Imports

**Order (each group separated by blank line):**
1. Standard library
2. Third-party (gi, etc.)
3. Local relative imports

### Naming Conventions

- **Classes**: `PascalCase` (e.g., `WallpaperApp`)
- **Functions/variables**: `snake_case` (e.g., `scan_wallpaper_dirs`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `ICON_SIZE`, `NORD`)

### Type Hints

Use type hints where they improve readability.

### Error Handling

- Use specific exception types when possible
- Return early with defaults for expected failures

### Docstrings

Use simple docstrings for public APIs.

### GTK Patterns

- Use `connect("signal-name", callback)` for signal handlers
- Use `GLib.timeout_add()` for periodic tasks

## File Structure

```
mados-wallpaper/
├── __init__.py          # Package info (version, app_id)
├── __main__.py          # Entry point
├── app.py               # Main WallpaperApp class
├── config.py            # Configuration constants
├── theme.py             # CSS theming (Nord palette)
├── wallpaper_scanner.py # Wallpaper scanning and compositor integration
├── AGENTS.md            # This file
```

## Adding New Features

1. Follow the existing code patterns
2. Add configuration to `config.py` if needed
3. Keep the Nord color scheme consistent
4. Test on both Sway and Hyprland if compositor-related
5. Handle missing dependencies gracefully