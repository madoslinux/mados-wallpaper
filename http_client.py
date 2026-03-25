"""HTTP client for mados-wallpaperd daemon REST API."""

import urllib.request
import urllib.error
import json
from typing import Any

DAEMON_URL = "http://127.0.0.1:18765"


def _request(method: str, path: str, data: dict | None = None) -> dict[str, Any] | None:
    """Make HTTP request to daemon."""
    url = f"{DAEMON_URL}{path}"
    try:
        if method == "GET":
            req = urllib.request.Request(url)
        else:  # POST
            req = urllib.request.Request(
                url,
                data=json.dumps(data or {}).encode(),
                headers={"Content-Type": "application/json"},
            )

        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        TimeoutError,
    ):
        return None


def daemon_running() -> bool:
    """Check if daemon is running."""
    return _request("GET", "/current") is not None


def get_all_wallpapers() -> list[dict[str, Any]]:
    """Get all wallpapers from daemon."""
    result = _request("GET", "/wallpapers")
    if result and "wallpapers" in result:
        return result["wallpapers"]
    return []


def get_current_workspace() -> int | None:
    """Get current workspace from daemon."""
    result = _request("GET", "/current")
    if result and "workspace" in result:
        return result["workspace"]
    return None


def get_wallpaper(workspace: int) -> dict[str, Any] | None:
    """Get wallpaper for workspace."""
    result = _request("GET", f"/wallpaper/{workspace}")
    return result


def set_wallpaper(
    workspace: int, path: str, mode: str = "fill"
) -> dict[str, Any] | None:
    """Set wallpaper for workspace via daemon."""
    return _request("POST", f"/wallpaper/{workspace}", {"path": path, "mode": mode})
