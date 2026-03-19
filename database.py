"""Database operations for mados-wallpaper - uses daemon as source of truth."""

import os
import subprocess
from typing import Any

DB_PATH = os.path.expanduser("~/.local/share/mados/wallpapers.db")


def _daemon_running() -> bool:
    try:
        result = subprocess.run(["pgrep", "-f", "mados-wallpaperd"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def init_db() -> None:
    """Initialize database through daemon."""
    if _daemon_running():
        subprocess.run(["mados-wallpaperd", "init"], capture_output=True, timeout=10)
    else:
        import sqlite3

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
        conn.commit()
        conn.close()


def sync_wallpapers() -> None:
    """Sync wallpapers through daemon."""
    if _daemon_running():
        subprocess.run(["mados-wallpaperd", "sync"], capture_output=True, timeout=10)
        return

    import sqlite3

    if not os.path.isfile(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH)
    wall_dir = os.path.expanduser("~/.local/share/mados/wallpapers")
    if os.path.isdir(wall_dir):
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
    conn.close()


def get_all_wallpapers() -> list[dict[str, Any]]:
    """Get all wallpapers from daemon or local DB."""
    if _daemon_running():
        result = subprocess.run(["mados-wallpaperd", "sync"], capture_output=True, timeout=10)

    if not os.path.isfile(DB_PATH):
        return []

    import sqlite3

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
    """Get workspace assignments from daemon or local DB."""
    if not os.path.isfile(DB_PATH):
        return {}

    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    assignments = {}
    for row in conn.execute("SELECT workspace, wallpaper_id, mode FROM assignments"):
        assignments[row["workspace"]] = {"wallpaper_id": row["wallpaper_id"], "mode": row["mode"]}
    conn.close()
    return assignments


def assign_wallpaper(workspace: int, wallpaper_id: int, mode: str = "fill") -> None:
    """Assign wallpaper through daemon."""
    import sqlite3

    if not os.path.isfile(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT path FROM wallpapers WHERE id = ?", (wallpaper_id,)).fetchone()
    conn.close()

    if row:
        wallpaper_path = row["path"]
        if _daemon_running():
            subprocess.run(
                ["mados-wallpaperd", "set", str(workspace), wallpaper_path, mode],
                capture_output=True,
                timeout=10,
            )
        else:
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

    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id, path FROM wallpapers WHERE id = ?", (wallpaper_id,)).fetchone()
    conn.close()

    if row:
        return {"id": row["id"], "path": row["path"], "filename": os.path.basename(row["path"])}
    return None


def get_connection():
    """Get direct database connection (for fallback)."""
    import sqlite3

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0, isolation_level="DEFERRED")
    conn.row_factory = sqlite3.Row
    return conn
