#!/usr/bin/env python3
"""Entry point for mados-wallpaper."""

import sys

from .app import WallpaperApp


def main() -> int:
    app = WallpaperApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())