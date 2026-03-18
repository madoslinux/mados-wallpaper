"""Main application for mados-wallpaper."""

import json
import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk

import __init__ as app_module
from config import CONFIG_DIR, MAX_WORKSPACES, STATE_FILE, WINDOW_WIDTH
from database import init_db, sync_wallpapers, get_all_wallpapers, get_assignments, assign_wallpaper, get_wallpaper_by_id, get_connection
from theme import COLORS
from workspace_card import WorkspaceCard

__app_id__ = app_module.__app_id__
__app_name__ = app_module.__app_name__


class WallpaperApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=__app_id__)
        self.connect("activate", self._on_activate)
        self._selected_workspace = 1
        self._load_state()

    def _on_activate(self, app):
        from gi.repository import GLib
        self._build_ui()
        
        def load_and_show():
            self._load_data()
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

    def _on_workspace_click(self, workspace: int):
        self._selected_workspace = workspace
        self._show_picker(workspace)

    def _show_picker(self, workspace: int):
        current_assignment = self._assignments.get(workspace, {})
        current_mode = current_assignment.get("mode", "fill")
        
        dialog = Gtk.FileDialog(title=f"Select Wallpaper for Workspace {workspace}")
        
        filter_images = Gtk.FileFilter()
        filter_images.set_name("Images")
        for ext in ["png", "jpg", "jpeg", "webp", "bmp", "gif"]:
            filter_images.add_pattern(f"*.{ext}")
        
        from gi.repository import Gio
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_images)
        dialog.set_filters(filters)
        
        mode_combo = Gtk.ComboBoxText()
        for mode, desc in [("fill", "Fill (cover)"), ("fit", "Fit"), ("center", "Center"), ("stretch", "Stretch"), ("tile", "Tile")]:
            mode_combo.append(mode, desc)
        mode_combo.set_active_id(current_mode)
        
        def on_response(dialog, result):
            try:
                file = dialog.open_finish(result)
                if file:
                    file_path = file.get_path()
                    mode = mode_combo.get_active_id()
                    
                    conn = get_connection()
                    conn.execute("INSERT OR IGNORE INTO wallpapers(path) VALUES(?)", (file_path,))
                    wallpaper_id = conn.execute("SELECT id FROM wallpapers WHERE path = ?", (file_path,)).fetchone()[0]
                    assign_wallpaper(workspace, wallpaper_id, mode)
                    conn.close()
                    
                    self._load_data()
                    self._save_state()
            except Exception as e:
                import traceback
                traceback.print_exc()
        
        dialog.open(self.window, None, on_response)

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

            card = WorkspaceCard(ws, wallpaper, self._on_workspace_click)
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

    def _build_ui(self):
        self.window = Gtk.ApplicationWindow(application=self, title="")
        self.window.set_default_size(580, 370)
        self.window.set_resizable(False)
        self.window.set_decorated(False)
        self.window.set_titlebar(None)
        self.window.set_css_classes(["main-window"])

        css = f"""
            .main-window {{
                border-radius: 20px;
            }}
            window {{
                background-color: {COLORS['bg_darkest']};
            }}
            .workspace-card {{
                background-color: {COLORS['bg_dark']}B3;
                border-radius: 16px;
                border: 1px solid {COLORS['bg_medium']};
                padding: 8px;
            }}
            .workspace-card.hovered {{
                background-color: {COLORS['bg_medium']};
                border: 1px solid {COLORS['accent']};
            }}
            .workspace-label {{
                color: {COLORS['accent']};
                font-weight: bold;
                font-size: 11px;
            }}
            .wallpaper-thumb {{
                border-radius: 10px;
            }}
            .wallpaper-name {{
                color: {COLORS['fg_dark']};
                font-size: 9px;
            }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

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


from gi.repository import GdkPixbuf


def main():
    app = WallpaperApp()
    return app.run(None)


if __name__ == "__main__":
    sys.exit(main())