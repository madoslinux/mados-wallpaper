"""Main application for mados-wallpaper."""

import os
import json
import sys
import traceback
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
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
        super().__init__(application_id=__app_id__, flags=Gio.ApplicationFlags.NON_UNIQUE)
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
                self.window.show()
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
                    ["swaymsg", "-t", "get_workspaces"], capture_output=True, text=True, timeout=5
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
                    ["hyprctl", "activeworkspace"], capture_output=True, text=True, timeout=5
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
                ["swaymsg", "-t", "subscribe", '["workspace"]'],
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
                        ws_data = event.get("current", {})
                        ws_name = ws_data.get("name", "1")
                        try:
                            new_ws = int(ws_name)
                        except ValueError:
                            new_ws = int(ws_name.split(":")[-1]) if ":" in ws_name else 1
                        if new_ws != self._current_workspace:
                            self._current_workspace = new_ws
                            GLib.idle_add(self._on_workspace_changed, new_ws)
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            print(f"hyprland watch error: {e}", file=sys.stderr)
        except KeyboardInterrupt:
            pass

    def _on_workspace_changed(self, workspace: int):
        if self._assignments.get(workspace):
            wallpaper = get_wallpaper_by_id(self._assignments[workspace]["wallpaper_id"])
            if wallpaper:
                self._apply_wallpaper(workspace)

    def _on_workspace_click(self, workspace: int):
        self._selected_workspace = workspace
        self._show_picker(workspace)

    def _apply_wallpaper(self, workspace: int):
        import subprocess

        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

        if "sway" in desktop:
            subprocess.run(["mados-sway-wallpaper-set", str(workspace)], check=False)
        elif "hyprland" in desktop:
            subprocess.run(["mados-hyprland-wallpaper-set", str(workspace)], check=False)

    def _on_mode_click(self, workspace: int, wallpaper: dict | None):
        if wallpaper:
            self._show_mode_selector(workspace, wallpaper["path"], wallpaper.get("mode", "fill"))

    def _show_picker(self, workspace: int):
        current_assignment = self._assignments.get(workspace, {})
        current_mode = current_assignment.get("mode", "fill")

        dialog = Gtk.FileDialog(title=f"Select Wallpaper - Workspace {workspace}")

        filter_images = Gtk.FileFilter()
        filter_images.set_name("Images")
        for ext in ["png", "jpg", "jpeg", "webp", "bmp", "gif"]:
            filter_images.add_pattern(f"*.{ext}")

        from gi.repository import Gio

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_images)
        dialog.set_filters(filters)

        def on_response(source, result):
            try:
                file = dialog.open_finish(result)
                if file:
                    file_path = file.get_path()
                    self._show_mode_selector(workspace, file_path, current_mode)
            except Exception:
                pass

        dialog.open(self.window, None, on_response)

    def _show_mode_selector(self, workspace: int, file_path: str, current_mode: str):
        mode_dialog = Gtk.Window(title="")
        mode_dialog.set_default_size(350, 180)
        mode_dialog.set_modal(True)
        mode_dialog.set_transient_for(self.window)
        mode_dialog.set_decorated(False)
        mode_dialog.set_css_classes(["main-window"])
        mode_dialog.set_application(self)

        mode_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        mode_box.set_margin_top(24)
        mode_box.set_margin_bottom(24)
        mode_box.set_margin_start(24)
        mode_box.set_margin_end(24)

        filename = os.path.basename(file_path)
        mode_label = Gtk.Label(label=f"Workspace {workspace}: {filename[:20]}")
        mode_label.set_halign(Gtk.Align.CENTER)
        mode_box.append(mode_label)

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
        mode_box.append(mode_combo)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: mode_dialog.destroy())
        btn_box.append(cancel_btn)

        save_btn = Gtk.Button(label="Save")
        save_btn.set_css_classes(["suggested-action"])

        def on_save(_):
            mode = mode_combo.get_active_id()
            conn = get_connection()
            conn.execute("INSERT OR IGNORE INTO wallpapers(path) VALUES(?)", (file_path,))
            wallpaper_id = conn.execute(
                "SELECT id FROM wallpapers WHERE path = ?", (file_path,)
            ).fetchone()[0]
            assign_wallpaper(workspace, wallpaper_id, mode)

            self._load_data()
            self._save_state()
            mode_dialog.destroy()

            self._apply_wallpaper(workspace)

        save_btn.connect("clicked", on_save)
        btn_box.append(save_btn)

        mode_box.append(btn_box)

        mode_dialog.set_child(mode_box)

        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect(
            "key-pressed",
            lambda c, k, kc, s: mode_dialog.destroy() if k == Gdk.KEY_Escape else False,
        )
        mode_dialog.add_controller(key_controller)

        mode_dialog.show()

    def _populate_grid(self):
        for child in self._grid:
            self._grid.remove(child)

        for ws in range(1, MAX_WORKSPACES + 1):
            assignment = self._assignments.get(ws)
            if assignment:
                wallpaper = get_wallpaper_by_id(assignment["wallpaper_id"])
                if wallpaper:
                    wallpaper["mode"] = assignment.get("mode", "fill")
            else:
                wallpaper = None

            card = WorkspaceCard(ws, wallpaper, self._on_workspace_click, self._on_mode_click)
            self._grid.attach(card, (ws - 1) % 3, (ws - 1) // 3, 1, 1)

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

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.window.close()
            return True
        return False

    def _build_ui(self):
        self.window = Gtk.ApplicationWindow(application=self, title="")
        self.window.set_default_size(580, 370)
        self.window.set_resizable(False)
        self.window.set_decorated(False)
        self.window.set_titlebar(None)
        self.window.set_css_classes(["main-window"])

        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.window.add_controller(key_controller)

        css = f"""
            .main-window {{
                border-radius: 0;
                background-color: {COLORS["bg_darkest"]}EE;
            }}
            window {{
                background-color: {COLORS["bg_darkest"]};
                border-radius: 0;
            }}
            .workspace-card {{
                background-color: {COLORS["bg_dark"]}CC;
                border-radius: 0;
                border: 2px solid {COLORS["bg_medium"]};
                padding: 12px;
            }}
            .workspace-card.hovered {{
                background-color: {COLORS["bg_medium"]};
                border: 2px solid {COLORS["accent"]};
            }}
            .workspace-label {{
                color: {COLORS["accent_teal"]};
                font-weight: bold;
                font-size: 12px;
            }}
            .wallpaper-thumb {{
                border-radius: 0;
            }}
            .wallpaper-name {{
                color: {COLORS["fg_dark"]};
                font-size: 10px;
            }}
            .wallpaper-mode {{
                color: {COLORS["accent_teal"]};
                font-size: 9px;
            }}
            .mode-button {{
                background-color: {COLORS["bg_medium"]};
                color: {COLORS["fg_light"]};
                border-radius: 0;
                border: 1px solid {COLORS["accent"]}66;
                padding: 4px 8px;
                font-size: 10px;
            }}
            .mode-button:hover {{
                background-color: {COLORS["accent"]};
                color: {COLORS["bg_darkest"]};
            }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._grid = Gtk.Grid()
        self._grid.set_column_spacing(20)
        self._grid.set_row_spacing(20)
        self._grid.set_margin_top(16)
        self._grid.set_margin_bottom(16)
        self._grid.set_margin_start(16)
        self._grid.set_margin_end(16)
        vbox.append(self._grid)

        self.window.set_child(vbox)


def main():
    app = WallpaperApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
