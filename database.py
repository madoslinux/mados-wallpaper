"""Database operations for mados-wallpaper - uses daemon HTTP API as source of truth."""

import os
import sqlite3
from typing import Any

from http_client import (
    daemon_running,
    get_all_wallpapers as http_get_all,
    set_wallpaper as http_set_wallpaper,
)

DB_PATH = os.path.expanduser("~/.local/share/mados/wallpapers.db")


def init_db() -> None:
    """Initialize database - daemon handles this on startup."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS wallpapers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS assignments (
        workspace INTEGER PRIMARY KEY,
        wallpaper_id INTEGER NOT NULL REFERENCES wallpapers(id),
        mode TEXT DEFAULT 'fill'
    )""")
    if not _column_exists(conn, "assignments", "mode"):
        conn.execute("ALTER TABLE assignments ADD COLUMN mode TEXT DEFAULT 'fill'")
    conn.commit()
    conn.close()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor)


def sync_wallpapers() -> None:
    """Sync wallpapers - daemon handles this."""
    if not os.path.isfile(DB_PATH):
        init_db()


def get_all_wallpapers() -> list[dict[str, Any]]:
    """Get all wallpapers from daemon via HTTP, fallback to local DB."""
    if daemon_running():
        wallpapers = http_get_all()
        if wallpapers is not None:
            return wallpapers

    if not os.path.isfile(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    wallpapers = []
    for row in conn.execute("SELECT id, path FROM wallpapers ORDER BY path"):
        wallpapers.append(
            {"id": row["id"], "path": row["path"], "filename": os.path.basename(row["path"])}
        )
    conn.close()
    return wallpapers


def get_assignments() -> dict[int, dict[str, Any]]:
    """Get workspace assignments from local DB."""
    if not os.path.isfile(DB_PATH):
        return {}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    assignments = {}
    for row in conn.execute("SELECT workspace, wallpaper_id, mode FROM assignments"):
        assignments[row["workspace"]] = {"wallpaper_id": row["wallpaper_id"], "mode": row["mode"]}
    conn.close()
    return assignments


def assign_wallpaper(workspace: int, wallpaper_id: int, mode: str = "fill") -> None:
    """Assign wallpaper via daemon HTTP API."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT path FROM wallpapers WHERE id = ?", (wallpaper_id,)).fetchone()

    if not row:
        conn.close()
        return

    wallpaper_path = row["path"]
    conn.close()

    if daemon_running():
        result = http_set_wallpaper(workspace, wallpaper_path, mode)
        if result is not None:
            return

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO assignments(workspace, wallpaper_id, mode) VALUES(?, ?, ?)",
        (workspace, wallpaper_id, mode),
    )
    conn.commit()
    conn.close()


def get_wallpaper_by_id(wallpaper_id: int) -> dict[str, Any] | None:
    """Get wallpaper path by ID from local DB."""
    if not os.path.isfile(DB_PATH):
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id, path FROM wallpapers WHERE id = ?", (wallpaper_id,)).fetchone()
    conn.close()

    if row:
        return {"id": row["id"], "path": row["path"], "filename": os.path.basename(row["path"])}
    return None


def get_connection():
    """Get direct database connection (for fallback)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0, isolation_level="DEFERRED")
    conn.row_factory = sqlite3.Row
    return conn
