#!/usr/bin/env python3
"""Minimal internal renderer IPC service.

This is an incremental foundation for the internal GL renderer path.
Current implementation handles IPC and compositor-native wallpaper apply,
while the OpenGL/layer-shell renderer is developed.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import threading


def detect_wm() -> str:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "sway" in desktop:
        return "sway"
    if "hypr" in desktop:
        return "hyprland"
    return "unknown"


def apply_compositor_wallpaper(path: str, mode: str) -> tuple[bool, str | None]:
    wm = detect_wm()
    if wm == "sway":
        try:
            cmd = ["swaymsg", "output", "*", "bg", path, mode]
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            if result.returncode == 0:
                return True, None
            err = result.stderr.decode().strip() if result.stderr else "swaymsg failed"
            return False, err
        except Exception as e:
            return False, str(e)

    if wm == "hyprland":
        try:
            cmd = ["hyprctl", "keyword", "monitor ,background", f"{path},{mode}"]
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            if result.returncode == 0:
                return True, None
            err = (
                result.stderr.decode().strip()
                if result.stderr
                else "hyprctl keyword failed"
            )
            return False, err
        except Exception as e:
            return False, str(e)

    return False, "unsupported compositor"


class RendererServer:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self._shutdown = threading.Event()
        self._state = {}

    def handle(self, payload: dict) -> dict:
        cmd = payload.get("cmd")
        if cmd == "health":
            return {"ok": True, "service": "internal_renderer", "gl": False}

        if cmd == "set_wallpaper":
            path = payload.get("path")
            mode = payload.get("mode", "fill")
            workspace = payload.get("workspace", 1)
            transition = payload.get("transition", {})
            shader_preset = payload.get("shader_preset", "none")

            if not path or not os.path.isfile(path):
                return {"ok": False, "error": "invalid path"}

            ok, error = apply_compositor_wallpaper(path, mode)
            if not ok:
                return {"ok": False, "error": error or "apply failed"}

            self._state[str(workspace)] = {
                "path": path,
                "mode": mode,
                "transition": transition,
                "shader_preset": shader_preset,
            }
            return {"ok": True}

        if cmd == "reload_outputs":
            return {"ok": True}

        return {"ok": False, "error": "unknown command"}

    def run(self):
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        server.listen(16)
        os.chmod(self.socket_path, 0o600)

        try:
            while not self._shutdown.is_set():
                conn, _ = server.accept()
                with conn:
                    data = b""
                    while True:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                        if b"\n" in data:
                            break

                    if not data:
                        continue

                    line = data.split(b"\n", 1)[0].decode(errors="ignore")
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        response = {"ok": False, "error": "invalid json"}
                    else:
                        response = self.handle(payload)

                    conn.sendall((json.dumps(response) + "\n").encode())
        finally:
            server.close()
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)


def main():
    parser = argparse.ArgumentParser(description="mados internal renderer")
    parser.add_argument("--socket", required=True, help="Renderer UNIX socket path")
    args = parser.parse_args()

    try:
        RendererServer(args.socket).run()
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"renderer error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
