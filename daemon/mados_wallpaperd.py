#!/usr/bin/env python3
"""
mados-wallpaperd - REST API daemon for wallpaper management
Only listens on localhost to avoid security issues.
"""

import os
import sys
import json
import sqlite3
import subprocess
import threading
import re
import time
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

DATA_DIR = os.path.expanduser("~/.local/share/mados")
DB_PATH = os.path.join(DATA_DIR, "wallpapers.db")
SYSTEM_WALLPAPERS = "/usr/share/backgrounds"
PID_FILE = os.path.join(DATA_DIR, "mados-wallpaperd.pid")
PORT = 18765  # Non-privileged port on localhost
LOG_FILE = "/var/log/mados-wallpaperd.log"
TRANSITION_TYPE = os.environ.get("MADOS_WALLPAPER_TRANSITION", "wipe")
TRANSITION_DURATION = os.environ.get("MADOS_WALLPAPER_TRANSITION_DURATION", "2.0")
SHADER_PRESET = os.environ.get("MADOS_WALLPAPER_SHADER_PRESET", "none")
RENDERER_BIN = os.environ.get(
    "MADOS_WALLPAPER_RENDERER_BIN", "mados-wallpaper-renderer"
)
REPO_RENDERER_BIN = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "renderer",
        "target",
        "release",
        "mados-wallpaper-renderer",
    )
)
REPO_RENDERER_BIN_DEBUG = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "renderer",
        "target",
        "debug",
        "mados-wallpaper-renderer",
    )
)
RENDERER_SOCKET = os.path.join(DATA_DIR, "renderer.sock")
RENDERER_START_TIMEOUT = 5.0


class InternalGlBackend:
    def __init__(self):
        self._renderer_process = None

    def _send(self, payload, timeout=2.0):
        if not os.path.exists(RENDERER_SOCKET):
            return None

        request = (json.dumps(payload) + "\n").encode()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(timeout)
                client.connect(RENDERER_SOCKET)
                client.sendall(request)

                response = b""
                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                    if b"\n" in response:
                        break
        except Exception as e:
            log(f"Renderer IPC error: {e}")
            return None

        if not response:
            return None

        try:
            return json.loads(response.decode().strip())
        except json.JSONDecodeError:
            return None

    def _renderer_running(self):
        result = self._send({"cmd": "health"})
        return bool(result and result.get("ok"))

    def _start_renderer(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(RENDERER_SOCKET):
            try:
                os.remove(RENDERER_SOCKET)
            except OSError:
                pass

        renderer_cmd = self._renderer_command()

        try:
            self._renderer_process = subprocess.Popen(
                renderer_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            log(f"Could not start renderer command '{renderer_cmd}': {e}")
            return False

        deadline = time.time() + RENDERER_START_TIMEOUT
        while time.time() < deadline:
            if self._renderer_running():
                return True
            time.sleep(0.1)
        return False

    def ensure_ready(self):
        if self._renderer_running():
            return True
        log("Renderer not reachable, starting internal renderer...")
        return self._start_renderer()

    def _renderer_command(self):
        configured = os.environ.get("MADOS_WALLPAPER_RENDERER_BIN")
        if configured:
            return [configured, "--socket", RENDERER_SOCKET]

        if os.path.isfile(REPO_RENDERER_BIN):
            return [REPO_RENDERER_BIN, "--socket", RENDERER_SOCKET]

        if os.path.isfile(REPO_RENDERER_BIN_DEBUG):
            return [REPO_RENDERER_BIN_DEBUG, "--socket", RENDERER_SOCKET]

        local_renderer = os.path.join(os.path.dirname(__file__), "renderer.py")
        if os.path.isfile(local_renderer):
            return [sys.executable, local_renderer, "--socket", RENDERER_SOCKET]

        return [RENDERER_BIN, "--socket", RENDERER_SOCKET]

    def apply(
        self,
        wallpaper_path,
        mode,
        workspace,
        transition_type,
        transition_duration,
        shader_preset,
    ):
        if not self.ensure_ready():
            log("Internal renderer unavailable")
            return False

        result = self._send(
            {
                "cmd": "set_wallpaper",
                "workspace": workspace,
                "path": wallpaper_path,
                "mode": mode,
                "transition": {
                    "type": transition_type,
                    "duration": transition_duration,
                },
                "shader_preset": shader_preset,
            },
            timeout=10.0,
        )
        if not result or not result.get("ok"):
            log(f"Renderer rejected wallpaper apply: {result}")
            return False
        return True

    def health(self):
        result = self._send({"cmd": "health"})
        return bool(result and result.get("ok"))


BACKEND = InternalGlBackend()


def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[mados-wallpaperd] [{timestamp}] {msg}"

    # Always print to stderr as backup
    print(formatted, file=sys.stderr, flush=True)

    # Try to write to /var/log
    try:
        os.makedirs("/var/log", exist_ok=True)
        with open(LOG_FILE, "a") as f:
            print(formatted, file=f, flush=True)
    except (PermissionError, IOError):
        pass


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
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
            mode TEXT DEFAULT 'fill',
            transition_type TEXT DEFAULT 'wipe',
            transition_duration REAL DEFAULT 2.0,
            shader_preset TEXT DEFAULT 'none'
        )
    """
    )
    # Add missing columns (migration)
    try:
        conn.execute("SELECT mode FROM assignments LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE assignments ADD COLUMN mode TEXT DEFAULT 'fill'")
    try:
        conn.execute("SELECT transition_type FROM assignments LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute(
            "ALTER TABLE assignments ADD COLUMN transition_type TEXT DEFAULT 'wipe'"
        )
    try:
        conn.execute("SELECT transition_duration FROM assignments LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute(
            "ALTER TABLE assignments ADD COLUMN transition_duration REAL DEFAULT 2.0"
        )
    try:
        conn.execute("SELECT shader_preset FROM assignments LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute(
            "ALTER TABLE assignments ADD COLUMN shader_preset TEXT DEFAULT 'none'"
        )
    conn.commit()
    conn.close()


def populate_from_system():
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM wallpapers").fetchone()[0]
    if count > 0:
        conn.close()
        return

    if not os.path.isdir(SYSTEM_WALLPAPERS):
        log(f"System wallpapers dir not found: {SYSTEM_WALLPAPERS}")
        conn.close()
        return

    import glob

    files = glob.glob(os.path.join(SYSTEM_WALLPAPERS, "*.png"))
    files += glob.glob(os.path.join(SYSTEM_WALLPAPERS, "*.jpg"))
    files += glob.glob(os.path.join(SYSTEM_WALLPAPERS, "*.jpeg"))
    files += glob.glob(os.path.join(SYSTEM_WALLPAPERS, "*.webp"))

    if not files:
        log(f"No wallpapers found in {SYSTEM_WALLPAPERS}")
        conn.close()
        return

    import random

    random.shuffle(files)

    inserted = 0
    for f in files:
        try:
            escaped = f.replace("'", "''")
            conn.execute(f"INSERT OR IGNORE INTO wallpapers(path) VALUES('{escaped}')")
            inserted += 1
        except Exception as e:
            log(f"Error inserting wallpaper: {e}")

    conn.commit()
    conn.close()
    log(f"Inserted {inserted} wallpapers from system")


def assign_random_wallpapers(max_ws=6):
    conn = sqlite3.connect(DB_PATH)
    wallpapers = conn.execute("SELECT id FROM wallpapers").fetchall()
    if not wallpapers:
        conn.close()
        log("No wallpapers to assign")
        return

    wallpapers = [w[0] for w in wallpapers]
    import random

    shuffled = random.sample(wallpapers, k=len(wallpapers))
    for i, ws in enumerate(range(1, max_ws + 1)):
        wp_id = shuffled[i % len(shuffled)]
        conn.execute(
            """
            INSERT OR REPLACE INTO assignments(
                workspace,
                wallpaper_id,
                mode,
                transition_type,
                transition_duration,
                shader_preset
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                ws,
                wp_id,
                "fill",
                TRANSITION_TYPE,
                float(TRANSITION_DURATION),
                SHADER_PRESET,
            ),
        )

    conn.commit()
    conn.close()
    log(f"Assigned random wallpapers to {max_ws} workspaces")


def detect_wm():
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "niri" in desktop:
        return "niri"
    elif "sway" in desktop:
        return "sway"
    elif "hypr" in desktop:
        return "hyprland"
    # Fallback checks
    try:
        subprocess.run(["swaymsg"], capture_output=True, timeout=2)
        return "sway"
    except Exception:
        pass
    try:
        subprocess.run(["hyprctl"], capture_output=True, timeout=2)
        return "hyprland"
    except Exception:
        pass
    return "unknown"


def parse_workspace_index(value):
    if value is None:
        return None
    try:
        ws = int(value)
        return ws if ws > 0 else None
    except (TypeError, ValueError):
        pass

    text = str(value).strip()
    match = re.match(r"^(\d+)", text)
    if match:
        return int(match.group(1))

    match = re.match(r"^name:(\d+)", text)
    if match:
        return int(match.group(1))

    return None


def extract_sway_workspace_index(workspace):
    ws_num = parse_workspace_index(workspace.get("num"))
    if ws_num is not None:
        return ws_num
    return parse_workspace_index(workspace.get("name"))


def get_niri_workspaces():
    socket_path = os.environ.get("NIRI_SOCKET", os.path.expanduser("~/.niri.sock"))
    if not os.path.exists(socket_path):
        return []

    import socket

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1)
    s.connect(socket_path)
    s.sendall(b'{"Workspaces":null}\n')
    data = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break
    s.close()
    resp = json.loads(data.decode())
    return resp.get("Ok", {}).get("Workspaces", [])


def resolve_niri_workspace_index(workspace_id):
    try:
        target_id = int(workspace_id)
    except (TypeError, ValueError):
        return None

    try:
        for ws in get_niri_workspaces():
            if ws.get("id") == target_id:
                idx = parse_workspace_index(ws.get("idx"))
                if idx is not None:
                    return idx
    except Exception:
        return None
    return None


def get_current_workspace(wm):
    try:
        if wm == "sway":
            result = subprocess.run(
                ["swaymsg", "-t", "get_workspaces"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            for ws in json.loads(result.stdout):
                if ws.get("focused"):
                    ws_index = extract_sway_workspace_index(ws)
                    if ws_index is not None:
                        return ws_index
        elif wm == "hyprland":
            result = subprocess.run(
                ["hyprctl", "-j", "activeworkspace"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode == 0 and result.stdout.strip():
                payload = json.loads(result.stdout)
                ws_index = parse_workspace_index(payload.get("name"))
                if ws_index is not None:
                    return ws_index
                ws_index = parse_workspace_index(payload.get("id"))
                if ws_index is not None:
                    return ws_index

            result = subprocess.run(
                ["hyprctl", "activeworkspace"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            match = re.search(r"workspace\s+ID\s+(-?\d+)", result.stdout)
            if match:
                ws_index = parse_workspace_index(match.group(1))
                if ws_index is not None:
                    return ws_index

            match = re.search(r"workspace\s+([^\n]+)", result.stdout)
            if match:
                ws_index = parse_workspace_index(match.group(1).strip())
                if ws_index is not None:
                    return ws_index
        elif wm == "niri":
            for ws in get_niri_workspaces():
                if ws.get("is_focused"):
                    ws_index = parse_workspace_index(ws.get("idx"))
                    if ws_index is not None:
                        return ws_index
    except Exception as e:
        log(f"Error getting workspace: {e}")
    return 1


def get_wallpaper_for_workspace(ws):
    try:
        conn = sqlite3.connect(DB_PATH)
        result = conn.execute(
            "SELECT w.path FROM wallpapers w JOIN assignments a ON w.id = a.wallpaper_id WHERE a.workspace = ?",
            (ws,),
        ).fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        log(f"Error getting wallpaper: {e}")
        return None


def get_mode_for_workspace(ws):
    try:
        conn = sqlite3.connect(DB_PATH)
        result = conn.execute(
            "SELECT mode FROM assignments WHERE workspace = ?", (ws,)
        ).fetchone()
        conn.close()
        return result[0] if result else "fill"
    except Exception:
        return "fill"


def get_render_settings_for_workspace(ws):
    try:
        conn = sqlite3.connect(DB_PATH)
        result = conn.execute(
            """
            SELECT mode, transition_type, transition_duration, shader_preset
            FROM assignments
            WHERE workspace = ?
            """,
            (ws,),
        ).fetchone()
        conn.close()
    except Exception as e:
        log(f"Error getting render settings: {e}")
        result = None

    if not result:
        return {
            "mode": "fill",
            "transition_type": TRANSITION_TYPE,
            "transition_duration": float(TRANSITION_DURATION),
            "shader_preset": SHADER_PRESET,
        }

    mode = result[0] or "fill"
    transition_type = result[1] or TRANSITION_TYPE
    transition_duration = result[2]
    shader_preset = result[3] or SHADER_PRESET
    try:
        transition_duration = float(transition_duration)
    except (TypeError, ValueError):
        transition_duration = float(TRANSITION_DURATION)

    return {
        "mode": mode,
        "transition_type": transition_type,
        "transition_duration": transition_duration,
        "shader_preset": shader_preset,
    }


def upsert_assignment(
    conn,
    workspace,
    wallpaper_id,
    mode,
    transition_type,
    transition_duration,
    shader_preset,
):
    conn.execute(
        """
        INSERT OR REPLACE INTO assignments(
            workspace,
            wallpaper_id,
            mode,
            transition_type,
            transition_duration,
            shader_preset
        ) VALUES(?, ?, ?, ?, ?, ?)
        """,
        (
            workspace,
            wallpaper_id,
            mode,
            transition_type,
            float(transition_duration),
            shader_preset,
        ),
    )


def apply_wallpaper(
    wp,
    mode="fill",
    workspace=1,
    transition_type=TRANSITION_TYPE,
    transition_duration=None,
    shader_preset=SHADER_PRESET,
):
    if not wp or not os.path.isfile(wp):
        log(f"Wallpaper not found: {wp}")
        return False

    if transition_duration is None:
        transition_duration = float(TRANSITION_DURATION)

    log(
        f"Applying wallpaper via internal renderer: {wp} "
        f"(ws={workspace}, mode={mode}, transition={transition_type}/{transition_duration}, shader={shader_preset})"
    )

    ok = BACKEND.apply(
        wp,
        mode,
        workspace,
        transition_type,
        transition_duration,
        shader_preset,
    )
    if ok:
        log("Wallpaper applied via internal renderer")
    else:
        log("Internal renderer apply failed")
    return ok


def watch_workspace_hyprland():
    log("Starting Hyprland workspace watcher")
    import socket

    while True:
        try:
            instance_sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
            xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")

            if instance_sig:
                socket_path = f"{xdg_runtime}/hypr/{instance_sig}/.socket2.sock"
            else:
                socket_path = f"{xdg_runtime}/hypr/.socket2.sock"

            log("Looking for Hyprland socket at: " + socket_path)

            if not os.path.exists(socket_path):
                log("Hyprland socket not found, trying hyprctl fallback...")
                time.sleep(2)
                continue

            log("Connecting to Hyprland socket...")
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(socket_path)
            s.sendall(b"subscribe workspace\n")
            s.settimeout(1)
            log("Hyprland subscription started")
            last_ws = get_current_workspace("hyprland")

            buffer = ""
            while True:
                try:
                    data = s.recv(4096).decode()
                    if not data:
                        log("Hyprland socket disconnected")
                        break
                    buffer += data
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        log(f"Hyprland event: {line}")
                        lowered = line.lower()
                        if not line or (
                            "workspace" not in lowered
                            and "focusedmon" not in lowered
                            and "focusedmonv2" not in lowered
                        ):
                            continue
                        try:
                            ws = get_current_workspace("hyprland")
                            if ws is None:
                                continue
                            if ws != last_ws:
                                log(f"Hyprland workspace changed: {last_ws} -> {ws}")
                                wp = get_wallpaper_for_workspace(ws)
                                settings = get_render_settings_for_workspace(ws)
                                if wp:
                                    apply_wallpaper(
                                        wp,
                                        settings["mode"],
                                        ws,
                                        settings["transition_type"],
                                        settings["transition_duration"],
                                        settings["shader_preset"],
                                    )
                                last_ws = ws
                        except (ValueError, IndexError) as e:
                            log(f"Hyprland parse error: {e} on line: {line}")
                except socket.timeout:
                    continue
            s.close()
            log("Hyprland socket closed, reconnecting...")
        except Exception as e:
            log(f"Hyprland watcher error: {e}")
        time.sleep(1)


def watch_workspace_niri():
    import socket
    import select

    socket_path = os.environ.get("NIRI_SOCKET", os.path.expanduser("~/.niri.sock"))
    last_ws = None

    while True:
        try:
            if not os.path.exists(socket_path):
                log("Niri socket not found, waiting...")
                time.sleep(2)
                continue

            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect(socket_path)
            s.sendall(b'{"EventStream":{"Filter":["Workspace"]}}\n')
            s.settimeout(1)

            log("Niri event stream connected")
            while True:
                try:
                    ready, _, _ = select.select([s], [], [], 5)
                    if ready:
                        data = s.recv(4096)
                        if not data:
                            log("Niri socket closed")
                            break
                        for line in data.decode().strip().split("\n"):
                            if not line.strip():
                                continue
                            try:
                                resp = json.loads(line)
                                event = resp.get("Event", {})
                                if "WorkspaceFocused" in event:
                                    focus_event = event["WorkspaceFocused"]
                                    ws = parse_workspace_index(focus_event.get("idx"))
                                    if ws is None:
                                        ws = resolve_niri_workspace_index(
                                            focus_event.get("id")
                                        )
                                    if ws is None:
                                        continue
                                    if ws != last_ws:
                                        log(
                                            f"Niri workspace changed: {last_ws} -> {ws}"
                                        )
                                        wp = get_wallpaper_for_workspace(ws)
                                        settings = get_render_settings_for_workspace(ws)
                                        if wp:
                                            apply_wallpaper(
                                                wp,
                                                settings["mode"],
                                                ws,
                                                settings["transition_type"],
                                                settings["transition_duration"],
                                                settings["shader_preset"],
                                            )
                                        last_ws = ws
                            except json.JSONDecodeError:
                                continue
                except socket.timeout:
                    continue
            s.close()
        except Exception as e:
            log(f"Niri watcher error: {e}")
            time.sleep(2)


def watch_workspace_sway():
    log("Starting Sway workspace watcher")
    while True:
        try:
            proc = subprocess.Popen(
                ["swaymsg", "-t", "subscribe", "-m", '["workspace"]'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            log("Sway subscription started")
            if proc.stdout is None:
                proc.wait(timeout=1)
                continue
            for line in proc.stdout:
                if not line or not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    ws = extract_sway_workspace_index(event.get("current", {}))
                    if ws:
                        log(f"Sway workspace event: {ws}")
                        wp = get_wallpaper_for_workspace(ws)
                        settings = get_render_settings_for_workspace(ws)
                        if wp:
                            apply_wallpaper(
                                wp,
                                settings["mode"],
                                ws,
                                settings["transition_type"],
                                settings["transition_duration"],
                                settings["shader_preset"],
                            )
                except json.JSONDecodeError:
                    pass
            log("Sway subscription ended, reconnecting...")
            proc.wait()
        except Exception as e:
            log(f"Sway watcher error: {e}")
        time.sleep(1)


class WallpaperHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress HTTP logging

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/wallpapers":
            conn = sqlite3.connect(DB_PATH)
            wallpapers = conn.execute("SELECT id, path FROM wallpapers").fetchall()
            conn.close()
            self.send_json(
                {"wallpapers": [{"id": w[0], "path": w[1]} for w in wallpapers]}
            )

        elif path == "/current":
            wm = detect_wm()
            ws = get_current_workspace(wm)
            self.send_json({"workspace": ws, "wm": wm})

        elif path.startswith("/wallpaper/"):
            try:
                ws = int(path.split("/")[-1])
            except ValueError:
                self.send_json({"error": "Invalid workspace"}, 400)
                return

            wp = get_wallpaper_for_workspace(ws)
            settings = get_render_settings_for_workspace(ws)
            self.send_json(
                {
                    "workspace": ws,
                    "path": wp,
                    "mode": settings["mode"],
                    "transition_type": settings["transition_type"],
                    "transition_duration": settings["transition_duration"],
                    "shader_preset": settings["shader_preset"],
                }
            )

        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if not path.startswith("/wallpaper/"):
            self.send_json({"error": "Not found"}, 404)
            return

        try:
            ws = int(path.split("/")[-1])
        except ValueError:
            self.send_json({"error": "Invalid workspace"}, 400)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, 400)
            return

        wp = data.get("path")
        mode = data.get("mode", "fill")
        transition_type = data.get("transition_type", TRANSITION_TYPE)
        transition_duration = data.get("transition_duration", TRANSITION_DURATION)
        shader_preset = data.get("shader_preset", SHADER_PRESET)

        try:
            transition_duration = float(transition_duration)
        except (TypeError, ValueError):
            transition_duration = float(TRANSITION_DURATION)

        wm = detect_wm()
        current_ws = get_current_workspace(wm)

        # Update DB if path provided
        if wp and os.path.isfile(wp):
            conn = sqlite3.connect(DB_PATH)

            # Get or insert wallpaper
            result = conn.execute(
                "SELECT id FROM wallpapers WHERE path = ?", (wp,)
            ).fetchone()
            if result:
                wp_id = result[0]
            else:
                escaped = wp.replace("'", "''")
                conn.execute(f"INSERT INTO wallpapers(path) VALUES('{escaped}')")
                wp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            upsert_assignment(
                conn,
                ws,
                wp_id,
                mode,
                transition_type,
                transition_duration,
                shader_preset,
            )
            conn.commit()
            conn.close()
            log(f"Updated DB: workspace {ws} = {wp}")

            # Apply if current workspace
            if ws == current_ws:
                apply_wallpaper(
                    wp,
                    mode,
                    ws,
                    transition_type,
                    transition_duration,
                    shader_preset,
                )
                self.send_json({"ok": True, "applied": True, "workspace": ws})
            else:
                self.send_json({"ok": True, "applied": False, "workspace": ws})
        else:
            # No path = apply from DB
            wp = get_wallpaper_for_workspace(ws)
            settings = get_render_settings_for_workspace(ws)

            if wp:
                apply_wallpaper(
                    wp,
                    settings["mode"],
                    ws,
                    settings["transition_type"],
                    settings["transition_duration"],
                    settings["shader_preset"],
                )
                self.send_json(
                    {
                        "ok": True,
                        "applied": True,
                        "workspace": ws,
                        "path": wp,
                        "mode": settings["mode"],
                        "transition_type": settings["transition_type"],
                        "transition_duration": settings["transition_duration"],
                        "shader_preset": settings["shader_preset"],
                    }
                )
            else:
                self.send_json(
                    {
                        "ok": True,
                        "applied": False,
                        "workspace": ws,
                        "error": "no wallpaper",
                    }
                )


def run_daemon():
    log(f"Starting daemon on localhost:{PORT}")

    # Init DB
    init_db()
    populate_from_system()

    # Assign wallpapers if needed
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
    conn.close()
    if count == 0:
        assign_random_wallpapers(6)

    # Apply current workspace wallpaper
    wm = detect_wm()
    ws = get_current_workspace(wm)
    wp = get_wallpaper_for_workspace(ws)
    settings = get_render_settings_for_workspace(ws)
    log(f"Current workspace: {ws}, wallpaper: {wp}")
    if wp:
        apply_wallpaper(
            wp,
            settings["mode"],
            ws,
            settings["transition_type"],
            settings["transition_duration"],
            settings["shader_preset"],
        )

    # Start workspace watcher in background
    if wm == "hyprland":
        threading.Thread(target=watch_workspace_hyprland, daemon=True).start()
    elif wm == "sway":
        threading.Thread(target=watch_workspace_sway, daemon=True).start()
    elif wm == "niri":
        threading.Thread(target=watch_workspace_niri, daemon=True).start()

    # Save PID
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # Start HTTP server
    server = HTTPServer(("127.0.0.1", PORT), WallpaperHandler)
    log(f"Daemon ready on http://localhost:{PORT}")
    server.serve_forever()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="mados-wallpaperd")
    parser.add_argument("-d", "--daemon", action="store_true", help="Start as daemon")
    parser.add_argument(
        "command",
        nargs="?",
        help=(
            "Command: list, get WS, set WS [PATH] [MODE] "
            "[TRANSITION_TYPE] [TRANSITION_DURATION] [SHADER_PRESET]"
        ),
    )
    parser.add_argument("args", nargs="*", help="Arguments for command")

    args = parser.parse_args()

    if args.command in ("list", "get", "set", "current"):
        # CLI mode - init DB and handle command directly
        init_db()
        populate_from_system()

        # Assign if needed
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
        conn.close()
        if count == 0:
            assign_random_wallpapers(6)

        if args.command == "list":
            conn = sqlite3.connect(DB_PATH)
            wallpapers = conn.execute("SELECT id, path FROM wallpapers").fetchall()
            conn.close()
            print(
                json.dumps(
                    {"wallpapers": [{"id": w[0], "path": w[1]} for w in wallpapers]}
                )
            )

        elif args.command == "current":
            wm = detect_wm()
            ws = get_current_workspace(wm)
            print(json.dumps({"workspace": ws, "wm": wm}))

        elif args.command == "get":
            if not args.args:
                print(json.dumps({"error": "workspace required"}))
            else:
                try:
                    ws = int(args.args[0])
                except ValueError:
                    print(json.dumps({"error": "invalid workspace"}))
                else:
                    wp = get_wallpaper_for_workspace(ws)
                    settings = get_render_settings_for_workspace(ws)
                    print(
                        json.dumps(
                            {
                                "workspace": ws,
                                "path": wp,
                                "mode": settings["mode"],
                                "transition_type": settings["transition_type"],
                                "transition_duration": settings["transition_duration"],
                                "shader_preset": settings["shader_preset"],
                            }
                        )
                    )

        elif args.command == "set":
            if not args.args:
                print(json.dumps({"error": "workspace required"}))
            else:
                try:
                    ws = int(args.args[0])
                except ValueError:
                    print(json.dumps({"error": "invalid workspace"}))
                else:
                    wp = args.args[1] if len(args.args) > 1 else None
                    mode = args.args[2] if len(args.args) > 2 else "fill"
                    transition_type = (
                        args.args[3] if len(args.args) > 3 else TRANSITION_TYPE
                    )
                    transition_duration = (
                        args.args[4] if len(args.args) > 4 else TRANSITION_DURATION
                    )
                    shader_preset = (
                        args.args[5] if len(args.args) > 5 else SHADER_PRESET
                    )
                    try:
                        transition_duration = float(transition_duration)
                    except (TypeError, ValueError):
                        transition_duration = float(TRANSITION_DURATION)

                    wm = detect_wm()
                    current_ws = get_current_workspace(wm)

                    if wp and os.path.isfile(wp):
                        conn = sqlite3.connect(DB_PATH)
                        result = conn.execute(
                            "SELECT id FROM wallpapers WHERE path = ?", (wp,)
                        ).fetchone()
                        if result:
                            wp_id = result[0]
                        else:
                            escaped = wp.replace("'", "''")
                            conn.execute(
                                f"INSERT INTO wallpapers(path) VALUES('{escaped}')"
                            )
                            wp_id = conn.execute(
                                "SELECT last_insert_rowid()"
                            ).fetchone()[0]
                        upsert_assignment(
                            conn,
                            ws,
                            wp_id,
                            mode,
                            transition_type,
                            transition_duration,
                            shader_preset,
                        )
                        conn.commit()
                        conn.close()

                        if ws == current_ws:
                            apply_wallpaper(
                                wp,
                                mode,
                                ws,
                                transition_type,
                                transition_duration,
                                shader_preset,
                            )
                            print(
                                json.dumps(
                                    {"ok": True, "applied": True, "workspace": ws}
                                )
                            )
                        else:
                            print(
                                json.dumps(
                                    {"ok": True, "applied": False, "workspace": ws}
                                )
                            )
                    else:
                        # No path = apply from DB
                        wp = get_wallpaper_for_workspace(ws)
                        settings = get_render_settings_for_workspace(ws)
                        if wp:
                            apply_wallpaper(
                                wp,
                                settings["mode"],
                                ws,
                                settings["transition_type"],
                                settings["transition_duration"],
                                settings["shader_preset"],
                            )
                            print(
                                json.dumps(
                                    {"ok": True, "applied": True, "workspace": ws}
                                )
                            )
                        else:
                            print(
                                json.dumps(
                                    {
                                        "ok": True,
                                        "applied": False,
                                        "workspace": ws,
                                        "error": "no wallpaper",
                                    }
                                )
                            )

    elif args.daemon:
        # Check if already running
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f:
                old_pid = int(f.read().strip())
            try:
                os.kill(old_pid, 0)
                log(f"Already running (PID: {old_pid})")
                sys.exit(0)
            except OSError:
                pass

        run_daemon()

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
