"""Configuration constants for mados-wallpaper."""

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

WALLPAPER_DIRS = [
    os.path.join(SCRIPT_DIR, "wallpapers"),
    os.path.expanduser("~/Imágenes"),
    os.path.expanduser("~/Pictures"),
    "/usr/share/backgrounds",
    "/usr/share/wayland-backgrounds",
]

CONFIG_DIR = os.path.expanduser("~/.config/mados-wallpaper")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")

DB_DIR = os.path.expanduser("~/.local/share/mados")
DB_PATH = os.path.join(DB_DIR, "wallpapers.db")

MAX_WORKSPACES = 6

WINDOW_WIDTH = 600
WINDOW_HEIGHT = 420