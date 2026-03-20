"""Main application for mados-wallpaper."""

import os
import json
import sys
import traceback
import subprocess
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, Gio, GLib

import __init__ as app_module
from config import CONFIG_DIR, MAX_WORKSPACES, STATE_FILE, WINDOW_WIDTH
from database import (
    init_db,
    sync_wallpapers,
    get_all_wallpapers,
    get_assignments,
    assign_wallpaper,
    get_wallpaper_by_id,
    get_connection,
)
from theme import COLORS
from workspace_card import WorkspaceCard

__app_id__ = app_module.__app_id__
__app_name__ = app_module.__app_name__


class WallpaperApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=__app_id__, flags=Gio.ApplicationFlags.NON_UNIQUE
        )
        self.connect("activate", self._on_activate)
        self._selected_workspace = 1
        self._current_workspace = 1
        self._workspace_watcher = None
        self._load_state()

    def _on_activate(self, app):
        try:
            from gi.repository import GLib

            self._build_ui()
        except Exception as e:
            print(f"ERROR in _on_activate: {e}", file=sys.stderr)
            traceback.print_exc()
            raise

        def load_and_show():
            self._load_data()
            self._start_workspace_watcher()
            if self.window:
                self.window.show_all()
                self.window.present()
            return False

        GLib.idle_add(load_and_show)

    def _load_data(self):
        init_db()
        sync_wallpapers()
        self._wallpapers = get_all_wallpapers()
        self._assignments = get_assignments()
        self._populate_grid()

    def _get_current_workspace(self) -> int:
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

        if "sway" in desktop:
            try:
                result = subprocess.run(
                    ["swaymsg", "-t", "get_workspaces"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                import json

                workspaces = json.loads(result.stdout)
                for ws in workspaces:
                    if ws.get("focused"):
                        return ws.get("num", 1)
            except Exception:
                pass
        elif "hyprland" in desktop:
            try:
                result = subprocess.run(
                    ["hyprctl", "activeworkspace"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in result.stdout.split("\n"):
                    if "workspace" in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "workspace" and i + 1 < len(parts):
                                ws = parts[i + 1]
                                if "(" in ws and ")" in ws:
                                    return int(ws.split("(")[1].split(")")[0])
                                return int(ws)
            except Exception:
                pass
        return 1

    def _start_workspace_watcher(self):
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

        if "sway" in desktop:
            self._current_workspace = self._get_current_workspace()
            thread = threading.Thread(target=self._sway_watch_loop, daemon=True)
            thread.start()
        elif "hyprland" in desktop:
            self._current_workspace = self._get_current_workspace()
            thread = threading.Thread(target=self._hyprland_watch_loop, daemon=True)
            thread.start()

    def _sway_watch_loop(self):
        try:
            process = subprocess.Popen(
                ["swaymsg", "-t", "subscribe", "-m", '["workspace"]'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            import json

            for line in process.stdout:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if event.get("change") == "focus":
                        new_ws = event.get("current", {}).get("num", 1)
                        if new_ws != self._current_workspace:
                            self._current_workspace = new_ws
                            GLib.idle_add(self._on_workspace_changed, new_ws)
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            print(f"sway watch error: {e}", file=sys.stderr)

    def _hyprland_watch_loop(self):
        try:
            process = subprocess.Popen(
                ["hyprctl", "subscribe", "workspace"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for line in process.stdout:
                if not line.strip() or "workspace" not in line.lower():
                    continue
                try:
                    parts = line.strip().split()
                    for i, part in enumerate(parts):
                        if part.startswith("workspace") or (
                            i > 0 and parts[i - 1] == "workspace"
                        ):
                            ws_str = parts[-1].split(">>")[-1].strip()
                            try:
                                new_ws = int(ws_str)
                            except ValueError:
                                new_ws = (
                                    int(ws_str.split(":")[-1]) if ":" in ws_str else 1
                                )
                            if new_ws != self._current_workspace:
                                self._current_workspace = new_ws
                                GLib.idle_add(self._on_workspace_changed, new_ws)
                            break
                except Exception:
                    continue
        except Exception as e:
            print(f"hyprland watch error: {e}", file=sys.stderr)
        except KeyboardInterrupt:
            pass

    def _on_workspace_changed(self, workspace: int):
        if self._assignments.get(workspace):
            wallpaper = get_wallpaper_by_id(
                self._assignments[workspace]["wallpaper_id"]
            )
            if wallpaper:
                self._apply_wallpaper(workspace)

    def _on_workspace_click(self, workspace: int):
        self._selected_workspace = workspace
        self._show_picker(workspace)

    def _apply_wallpaper(self, workspace: int):
        import subprocess

        # Get wallpaper path for this workspace
        assignment = self._assignments.get(workspace)
        if not assignment:
            return

        wallpaper_id = assignment.get("wallpaper_id")
        if not wallpaper_id:
            return

        wallpaper = get_wallpaper_by_id(int(wallpaper_id))
        if not wallpaper:
            return

        print(f"[DEBUG] _apply_wallpaper called for workspace {workspace}")
        wallpaper_path = wallpaper["path"]
        mode = assignment.get("mode", "fill")
        print(f"[DEBUG] wallpaper_path={wallpaper_path}, mode={mode}")

        # Try daemon first, fallback to direct methods
        try:
            result = subprocess.run(
                ["pgrep", "-f", "mados-wallpaperd"], capture_output=True, timeout=5
            )
            print(f"[DEBUG] pgrep result: returncode={result.returncode}")
            if result.returncode == 0:
                subprocess.run(
                    ["mados-wallpaperd", "set", str(workspace), wallpaper_path, mode],
                    capture_output=True,
                    timeout=10,
                )
                print(
                    f"[DEBUG] Sent to daemon: mados-wallpaperd set {workspace} {wallpaper_path} {mode}"
                )
                return
        except Exception as e:
            print(f"[DEBUG] Daemon communication failed: {e}")

        # Fallback to direct methods
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        print(f"[DEBUG] Desktop: {desktop}")
        cmd = None
        if "sway" in desktop:
            cmd = "mados-sway-wallpaper-set"
        elif "hyprland" in desktop:
            cmd = "mados-hyprland-wallpaper-set"
        if cmd:
            import shutil

            if shutil.which(cmd):
                subprocess.run([cmd, str(workspace)], capture_output=True, check=False)
                print(f"[DEBUG] Called {cmd} {workspace}")
            else:
                print(f"[DEBUG] {cmd} not found in PATH")

    def _on_mode_click(self, workspace: int, wallpaper: dict | None):
        if wallpaper:
            self._show_mode_selector(
                workspace, wallpaper["path"], wallpaper.get("mode", "fill")
            )

    def _show_picker(self, workspace: int):
        current_assignment = self._assignments.get(workspace, {})
        current_mode = current_assignment.get("mode", "fill")

        dialog = Gtk.FileChooserDialog(
            title=f"Select Wallpaper - Workspace {workspace}",
            parent=self.window,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )

        filter_images = Gtk.FileFilter()
        filter_images.set_name("Images")
        for ext in ["png", "jpg", "jpeg", "webp", "bmp", "gif"]:
            filter_images.add_pattern(f"*.{ext}")

        dialog.add_filter(filter_images)

        def on_response(dialog, response):
            if response == Gtk.ResponseType.OK:
                file_path = dialog.get_filename()
                if file_path:
                    self._show_mode_selector(workspace, file_path, current_mode)
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _show_mode_selector(self, workspace: int, file_path: str, current_mode: str):
        mode_dialog = Gtk.Window(title="")
        mode_dialog.set_default_size(350, 180)
        mode_dialog.set_modal(True)
        mode_dialog.set_transient_for(self.window)
        mode_dialog.set_decorated(False)
        mode_dialog.get_style_context().add_class("main-window")
        mode_dialog.set_application(self)

        mode_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        mode_box.set_margin_top(24)
        mode_box.set_margin_bottom(24)
        mode_box.set_margin_start(24)
        mode_box.set_margin_end(24)

        filename = os.path.basename(file_path)
        mode_label = Gtk.Label(label=f"Workspace {workspace}: {filename[:20]}")
        mode_label.set_halign(Gtk.Align.CENTER)
        mode_box.pack_start(mode_label, False, False, 0)

        mode_combo = Gtk.ComboBoxText()
        for mode, desc in [
            ("fill", "Fill (cover screen)"),
            ("fit", "Fit (keep aspect)"),
            ("center", "Center"),
            ("stretch", "Stretch"),
            ("tile", "Tile"),
        ]:
            mode_combo.append(mode, desc)
        mode_combo.set_active_id(current_mode)
        mode_box.pack_start(mode_combo, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: mode_dialog.destroy())
        btn_box.pack_start(cancel_btn, False, False, 0)

        save_btn = Gtk.Button(label="Save")
        save_btn.get_style_context().add_class("suggested-action")

        def on_save(_):
            mode = mode_combo.get_active_id()
            conn = get_connection()
            conn.execute(
                "INSERT OR IGNORE INTO wallpapers(path) VALUES(?)", (file_path,)
            )
            wallpaper_id = conn.execute(
                "SELECT id FROM wallpapers WHERE path = ?", (file_path,)
            ).fetchone()[0]
            conn.close()
            assign_wallpaper(workspace, wallpaper_id, mode)
            self._load_data()
            self._save_state()
            mode_dialog.destroy()

            self._apply_wallpaper(workspace)

        save_btn.connect("clicked", on_save)
        btn_box.pack_start(save_btn, False, False, 0)

        mode_box.pack_start(btn_box, False, False, 0)

        mode_dialog.add(mode_box)

        mode_dialog.connect(
            "key-press-event",
            lambda w, e: mode_dialog.destroy() if e.keyval == Gdk.KEY_Escape else False,
        )

        mode_dialog.show_all()

    def _populate_grid(self):
        for child in self._grid.get_children():
            self._grid.remove(child)

        for ws in range(1, MAX_WORKSPACES + 1):
            assignment = self._assignments.get(ws)
            if assignment:
                wallpaper = get_wallpaper_by_id(assignment["wallpaper_id"])
                if wallpaper:
                    wallpaper["mode"] = assignment.get("mode", "fill")
            else:
                wallpaper = None

            card = WorkspaceCard(
                ws, wallpaper, self._on_workspace_click, self._on_mode_click
            )
            self._grid.attach(card, (ws - 1) % 3, (ws - 1) // 3, 1, 1)
        self._grid.show_all()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
                    self._selected_workspace = state.get("last_workspace", 1)
            except (json.JSONDecodeError, IOError):
                self._selected_workspace = 1

    def _save_state(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({"last_workspace": self._selected_workspace}, f)

    def _on_key_pressed(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.window.close()
            return True
        return False

    def _build_ui(self):
        self.window = Gtk.ApplicationWindow(application=self, title="")
        self.window.set_default_size(580, 370)
        self.window.set_resizable(False)
        self.window.set_decorated(False)
        self.window.set_titlebar(None)

        accel_group = Gtk.AccelGroup()
        self.window.add_accel_group(accel_group)
        self.window.connect("key-press-event", self._on_key_pressed)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._grid = Gtk.Grid()
        self._grid.set_column_spacing(20)
        self._grid.set_row_spacing(20)
        self._grid.set_margin_top(16)
        self._grid.set_margin_bottom(16)
        self._grid.set_margin_start(16)
        self._grid.set_margin_end(16)
        vbox.pack_start(self._grid, True, True, 0)

        self.window.add(vbox)


def main():
    app = WallpaperApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
