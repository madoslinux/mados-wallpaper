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
from database import init_db, sync_wallpapers, get_all_wallpapers, get_assignments, assign_wallpaper, get_wallpaper_by_id
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
        self._build_ui()
        self._load_data()
        self.window.present()

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
        dialog = Gtk.Window(title=f"Wallpaper for Workspace {workspace}")
        dialog.set_default_size(550, 450)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)

        mode_combo = Gtk.ComboBoxText()
        for mode, desc in [("fill", "Fill"), ("fit", "Fit"), ("center", "Center"), ("stretch", "Stretch"), ("tile", "Tile")]:
            mode_combo.append(mode, desc)
        mode_combo.set_active_id("fill")
        box.append(mode_combo)

        scroll = Gtk.ScrolledWindow()
        flowbox = Gtk.FlowBox()
        flowbox.set_max_children_per_line(3)
        flowbox.set_halign(Gtk.Align.CENTER)

        current_assignment = self._assignments.get(workspace, {})
        current_mode = current_assignment.get("mode", "fill")
        mode_combo.set_active_id(current_mode)

        def on_item_click(wp):
            mode = mode_combo.get_active_id()
            assign_wallpaper(workspace, wp["id"], mode)
            self._assignments[workspace] = {"wallpaper_id": wp["id"], "mode": mode}
            self._populate_grid()
            self._save_state()
            dialog.destroy()

        for wp in self._wallpapers:
            item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            item.set_size_request(140, 100)

            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(wp["path"], 130, 70, True)
                pic = Gtk.Picture.new_for_pixbuf(pixbuf)
            except Exception:
                pic = Gtk.Image.new_from_icon_name("image-x-generic")

            item.append(pic)
            item.append(Gtk.Label(label=wp["filename"][:18]))

            click = Gtk.GestureClick.new()
            click.connect("pressed", lambda g, n, x, y, wp=wp: on_item_click(wp))
            item.add_controller(click)

            flowbox.append(item)

        scroll.set_child(flowbox)
        box.append(scroll)

        dialog.set_child(box)
        dialog.show()

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
        self.window = Gtk.ApplicationWindow(application=self, title=__app_name__)
        self.window.set_default_size(WINDOW_WIDTH, 420)

        css = f"""
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

        header = Gtk.Label(label=__app_name__)
        header.set_markup(f"<span weight='bold' size='large'>{__app_name__}</span>")
        header.set_halign(Gtk.Align.START)
        header.set_margin_top(12)
        header.set_margin_start(12)
        vbox.append(header)

        self._grid = Gtk.Grid()
        self._grid.set_column_spacing(12)
        self._grid.set_row_spacing(16)
        self._grid.set_margin_top(12)
        self._grid.set_margin_bottom(12)
        self._grid.set_margin_start(12)
        self._grid.set_margin_end(12)
        vbox.append(self._grid)

        self.window.set_child(vbox)


from gi.repository import GdkPixbuf


def main():
    app = WallpaperApp()
    return app.run(None)


if __name__ == "__main__":
    sys.exit(main())