#!/usr/bin/env python3
"""Entry point for mados-wallpaper."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import main

if __name__ == "__main__":
    sys.exit(main())
