"""Database operations for mados-wallpaper."""

import os
import sqlite3
from typing import Any

from config import DB_PATH, WALLPAPER_DIRS

_conn = None


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, timeout=10.0, isolation_level="DEFERRED")
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
    return _conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wallpapers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL
        )
    """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assignments (
            workspace INTEGER PRIMARY KEY,
            wallpaper_id INTEGER NOT NULL REFERENCES wallpapers(id),
            mode TEXT DEFAULT 'fill'
        )
    """
    )
    conn.commit()


def sync_wallpapers() -> None:
    conn = get_connection()
    for wall_dir in WALLPAPER_DIRS:
        if not os.path.isdir(wall_dir):
            continue
        for root, _, files in os.walk(wall_dir):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in (".png", ".jpg", ".jpeg", ".webp"):
                    path = os.path.join(root, filename)
                    try:
                        conn.execute("INSERT OR IGNORE INTO wallpapers(path) VALUES(?)", (path,))
                    except sqlite3.Error:
                        pass
    conn.commit()


def get_all_wallpapers() -> list[dict[str, Any]]:
    conn = get_connection()
    wallpapers = []
    for row in conn.execute("SELECT id, path FROM wallpapers ORDER BY path"):
        wallpapers.append({"id": row["id"], "path": row["path"], "filename": os.path.basename(row["path"])})
    return wallpapers


def get_assignments() -> dict[int, dict[str, Any]]:
    conn = get_connection()
    assignments = {}
    for row in conn.execute("SELECT workspace, wallpaper_id, mode FROM assignments"):
        assignments[row["workspace"]] = {"wallpaper_id": row["wallpaper_id"], "mode": row["mode"]}
    return assignments


def assign_wallpaper(workspace: int, wallpaper_id: int, mode: str = "fill") -> None:
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO assignments(workspace, wallpaper_id, mode) VALUES(?, ?, ?)", (workspace, wallpaper_id, mode))
    conn.commit()


def get_wallpaper_by_id(wallpaper_id: int) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute("SELECT id, path FROM wallpapers WHERE id = ?", (wallpaper_id,)).fetchone()
    if row:
        return {"id": row["id"], "path": row["path"], "filename": os.path.basename(row["path"])}
    return None