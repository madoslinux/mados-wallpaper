"""Configuration constants for mados-wallpaper."""

import os

NORD = {
    "polar_night": {
        "darkest": "#2e3440",
        "darker": "#3b4252",
        "dark": "#434c5e",
        "light": "#4c566a",
    },
    "snow_storm": {
        "darkest": "#d8dee9",
        "darker": "#e5e9f0",
        "dark": "#eceff4",
        "light": "#8fbcbb",
    },
    "frost": {
        "cold": "#8fbcbb",
        "teal": "#88c0d0",
        "cyan": "#81a1c1",
        "blue": "#5e81ac",
    },
    "aurora": {
        "red": "#bf616a",
        "orange": "#d08770",
        "yellow": "#ebcb8b",
        "green": "#a3be8c",
        "purple": "#b48ead",
    },
}

WALLPAPER_DIRS = [
    os.path.expanduser("~/Imágenes"),
    os.path.expanduser("~/Pictures"),
    "/usr/share/backgrounds",
    "/usr/share/wayland-backgrounds",
]

CONFIG_DIR = os.path.expanduser("~/.config/mados-wallpaper")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")

ICON_SIZE = 48
WINDOW_WIDTH = 400
WINDOW_HEIGHT = 500