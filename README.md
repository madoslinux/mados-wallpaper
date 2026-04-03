# madOS Wallpaper

A GTK3-based wallpaper manager for madOS that manages per-workspace wallpapers using SQLite.

## Features

- Manage wallpapers for 6 workspaces
- Reads/writes to SQLite database (`~/.local/share/mados/wallpapers.db`)
- Wallpapers are assigned randomly on first run
- Persists assignments across reboots
- Nord theme with consistent color palette
- Daemon-backed wallpaper apply with internal renderer IPC

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

## Daemon + Internal Renderer

`mados-wallpaperd` now applies wallpapers through an internal renderer IPC backend.

- Daemon socket client target: `~/.local/share/mados/renderer.sock`
- Default transition: `wipe` with `2.0s`
- Default shader preset: `none`

The daemon auto-starts the renderer process if needed.

Renderer startup priority:
- `MADOS_WALLPAPER_RENDERER_BIN` (if set)
- `renderer/target/release/mados-wallpaper-renderer`
- `renderer/target/debug/mados-wallpaper-renderer`
- Python fallback: `daemon/renderer.py`

Environment variables:
- `MADOS_WALLPAPER_TRANSITION` (default: `wipe`)
- `MADOS_WALLPAPER_TRANSITION_DURATION` (default: `2.0`)
- `MADOS_WALLPAPER_SHADER_PRESET` (default: `none`)
- `MADOS_WALLPAPER_RENDERER_BIN` (optional custom renderer binary)

### Build Rust renderer

```bash
cd renderer
cargo build --release
```

After that, running `mados-wallpaperd` will pick `renderer/target/release/mados-wallpaper-renderer` automatically.

Optional experimental build with Wayland GL scaffold:

```bash
cd renderer
cargo build --release --features wayland_gl
```

This enables protocol probing hooks for the upcoming `layer-shell + EGL/GLSL` renderer path.

Renderer backend selection:
- `MADOS_RENDERER_BACKEND=auto` (default, prefers `wayland_gl` when available)
- `MADOS_RENDERER_BACKEND=wayland_gl`
- `MADOS_RENDERER_BACKEND=shell`

KDE/KWin note:
- In `auto` mode on KDE/Plasma sessions, renderer defaults to `shell` backend for reliable wallpaper apply via Plasma DBus (`qdbus6`/`qdbus`).

Current `wayland_gl` status:
- Initializes Wayland connection and tracks outputs + layer-shell availability.
- Maintains per-output surface slots and wallpaper request state.
- Creates `wl_surface` + `zwlr_layer_surface_v1` per output in background layer.
- Commits a temporary `wl_shm` solid-color buffer per output to validate native surface rendering path.
- Uploads decoded wallpaper pixels to `wl_shm` buffers (cover/crop fit) and commits them on each output.
- `wayland_gl` no longer uses compositor command fallback (`swaymsg`/`hyprctl`) for apply.
- Includes GPU init probe in `renderer/src/gpu_pipeline.rs` that validates EGL + GL shared libraries and performs `eglGetDisplay/eglInitialize` version probing.
- Includes EGL context + pbuffer setup and GL shader program scaffolding, with transition state (`wipe`, 2.0s) advanced per upload.
- Supports renderer commands `set_transition` and `set_shader_preset`; transition and preset are applied in GPU pipeline state.
- Applies visible native transition/shader path on output surfaces via CPU-backed frame pipeline (`wipe` blend frames + preset tint), while EGL on-screen presentation is finalized.
- `wipe` transition duration now follows workspace config (`transition_duration`), and shader presets include `none`, `nord`, and `cinematic`.
- IPC server now dispatches `set_wallpaper` asynchronously to a worker thread, so long transitions no longer block socket responsiveness.
- Worker queue has bounded capacity and deduplicates pending async `set_wallpaper` requests by workspace (latest request wins).
- Transition frame pacing now uses Wayland frame callbacks instead of fixed sleeps; control/status responses include runtime details (`health`, `get_state`).
- Runtime status includes last async apply result and error cause for easier debugging from IPC clients.
- Runtime counters exposed in status details: queued/applied/failed/dropped async jobs.
- Health details now include backend diagnostics (Wayland/layer-shell/output counts, EGL version, GPU/runtime errors) to troubleshoot KDE/KWin environments.

Known remaining limitation:
- Final on-screen presentation still uses `wl_shm` buffers; GPU pipeline currently runs in parallel (EGL pbuffer path) and is not yet the direct presenter to `wl_surface`.

## Database

The app uses a SQLite database at `~/.local/share/mados/wallpapers.db`:

- **wallpapers**: id, path
- **assignments**: workspace (1-6), wallpaper_id
- **assignments**: workspace (1-6), wallpaper_id, mode, transition_type, transition_duration, shader_preset

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
