"""Wallpaper scanning and management utilities."""

import os
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


@dataclass(slots=True)
class Wallpaper:
    path: str
    filename: str
    width: int
    height: int


def scan_wallpaper_dirs(dirs: list[str]) -> list[Wallpaper]:
    wallpapers = []
    for directory in dirs:
        if not os.path.isdir(directory):
            continue
        for root, _, files in os.walk(directory):
            for filename in files:
                path = os.path.join(root, filename)
                ext = Path(filename).suffix.lower()
                if ext in SUPPORTED_EXTENSIONS:
                    wallpapers.append(Wallpaper(path=path, filename=filename, width=0, height=0))
    return wallpapers


def set_sway_wallpaper(image_path: str, mode: str = "fill") -> bool:
    import subprocess

    mode_map = {
        "fill": "fill",
        "fit": "fit",
        "stretch": "stretch",
        "center": "center",
        "tile": "tile",
        "solid_color": "solid_color",
    }
    sway_mode = mode_map.get(mode, "fill")

    try:
        subprocess.run(
            ["swaymsg", "output", "*", "bg", image_path, sway_mode],
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def set_hyprland_wallpaper(image_path: str, monitor: str = "") -> bool:
    import subprocess

    monitor_flag = f"monitor {monitor}," if monitor else ""
    try:
        subprocess.run(
            ["hyprctl", "keyword", f"{monitor_flag}background", image_path, "fill"],
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def detect_compositor() -> str | None:
    import subprocess

    compositor = os.environ.get("SWAYSOCK") or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if compositor:
        if "SWAYSOCK" in os.environ:
            return "sway"
        if "HYPRLAND_INSTANCE_SIGNATURE" in os.environ:
            return "hyprland"
    try:
        result = subprocess.run(["pgrep", "-x", "sway"], capture_output=True)
        if result.returncode == 0:
            return "sway"
    except FileNotFoundError:
        pass
    try:
        result = subprocess.run(["pgrep", "-x", "Hyprland"], capture_output=True)
        if result.returncode == 0:
            return "hyprland"
    except FileNotFoundError:
        pass
    return None