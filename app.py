#!/usr/bin/env python3
"""Main application for mados-wallpaper."""

import json
import os
import sqlite3

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf

import __init__ as app_module
from config import (
    CONFIG_DIR,
    DB_PATH,
    MAX_WORKSPACES,
    STATE_FILE,
    WALLPAPER_DIRS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from theme import get_css

__app_id__ = app_module.__app_id__
__app_name__ = app_module.__app_name__
__version__ = app_module.__version__


class WallpaperApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=__app_id__)
        self.connect("activate", self._on_activate)
        self._wallpapers = []
        self._assignments = {}
        self._selected_workspace = 1
        self._load_state()

    def _on_activate(self, _app: Gtk.Application) -> None:
        self._build_ui()
        self._load_from_db()
        self._apply_css()
        self.window.show_all()

    def _apply_css(self) -> None:
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(get_css())
        screen = Gdk.Screen.get_default()
        if screen:
            context = Gtk.StyleContext()
            context.add_provider_for_screen(screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _get_db_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_db_connection()
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
                mode TEXT DEFAULT 'fill'
            )
        """
        )
        conn.commit()
        conn.close()

    def _sync_wallpapers(self) -> None:
        conn = self._get_db_connection()
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
        conn.close()

    def _load_from_db(self) -> None:
        self._init_db()
        self._sync_wallpapers()

        conn = self._get_db_connection()

        self._wallpapers = []
        for row in conn.execute("SELECT id, path FROM wallpapers ORDER BY path"):
            self._wallpapers.append({"id": row["id"], "path": row["path"], "filename": os.path.basename(row["path"])})

        self._assignments = {}
        for row in conn.execute("SELECT workspace, wallpaper_id, mode FROM assignments"):
            self._assignments[row["workspace"]] = {"wallpaper_id": row["wallpaper_id"], "mode": row["mode"]}

        conn.close()

        self._populate_grid()

    def _get_wallpaper_for_workspace(self, workspace: int) -> dict | None:
        assignment = self._assignments.get(workspace)
        if not assignment:
            return None
        wallpaper_id = assignment["wallpaper_id"]
        mode = assignment.get("mode", "fill")
        for wp in self._wallpapers:
            if wp["id"] == wallpaper_id:
                return {"id": wp["id"], "path": wp["path"], "filename": wp["filename"], "mode": mode}
        return None

    def _populate_grid(self) -> None:
        for child in self._grid.get_children():
            self._grid.remove(child)

        for ws in range(1, MAX_WORKSPACES + 1):
            wallpaper = self._get_wallpaper_for_workspace(ws)
            item = self._create_workspace_item(ws, wallpaper)
            self._grid.attach(item, (ws - 1) % 3, (ws - 1) // 3, 1, 1)

    def _create_workspace_item(self, workspace: int, wallpaper: dict | None) -> Gtk.EventBox:
        event_box = Gtk.EventBox()
        event_box.set_property("width-request", 180)
        event_box.set_property("height-request", 160)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        ws_label = Gtk.Label()
        ws_label.set_markup(f"<span weight='bold'>Workspace {workspace}</span>")
        ws_label.set_name("workspace-label")
        vbox.pack_start(ws_label, False, False, 0)

        if wallpaper and os.path.exists(wallpaper["path"]):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(wallpaper["path"], 170, 110, True)
                image = Gtk.Image.new_from_pixbuf(pixbuf)
            except Exception:
                image = Gtk.Image.new_from_icon_name("image-x-generic", Gtk.IconSize.DIALOG)
        else:
            image = Gtk.Image.new_from_icon_name("image-missing", Gtk.IconSize.DIALOG)
            image.set_property("pixel-size", 48)

        image.set_name("wallpaper-thumb")
        vbox.pack_start(image, True, True, 0)

        filename = wallpaper["filename"] if wallpaper else "No wallpaper"
        label = Gtk.Label(label=filename)
        label.set_name("wallpaper-filename")
        label.set_ellipsize(2)
        label.set_property("max-width-chars", 22)
        vbox.pack_start(label, False, False, 0)

        event_box.add(vbox)
        event_box.connect("button-press-event", self._on_workspace_clicked, workspace)

        return event_box

    def _on_workspace_clicked(self, widget: Gtk.Widget, event: Gdk.Event, workspace: int) -> None:
        self._selected_workspace = workspace
        self._show_wallpaper_picker(workspace)

    def _show_wallpaper_picker(self, workspace: int) -> None:
        current_assignment = self._assignments.get(workspace, {})
        current_mode = current_assignment.get("mode", "fill")

        dialog = Gtk.Dialog(title=f"Select Wallpaper for Workspace {workspace}", parent=self.window, flags=0)
        dialog.set_default_size(550, 450)

        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Select", Gtk.ResponseType.OK)

        content = dialog.get_content_area()

        mode_box = Gtk.Box(spacing=8)
        mode_box.set_property("margin", 12)

        mode_label = Gtk.Label(label="Display mode:")
        mode_label.set_property("halign", Gtk.Align.START)
        mode_box.pack_start(mode_label, False, False, 0)

        mode_combo = Gtk.ComboBoxText()
        modes = [("fill", "Fill (cover screen)"), ("fit", "Fit (keep aspect)"), ("center", "Center"), ("stretch", "Stretch"), ("tile", "Tile")]
        for mode_value, mode_desc in modes:
            mode_combo.append(mode_value, mode_desc)
        mode_combo.set_active_id(current_mode)
        mode_box.pack_start(mode_combo, False, False, 0)

        content.pack_start(mode_box, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_property("margin", 8)

        flowbox = Gtk.FlowBox()
        flowbox.set_valign(Gtk.Align.START)
        flowbox.set_max_children_per_line(3)
        flowbox.set_property("margin", 8)

        for wp in self._wallpapers:
            item = self._create_picker_item(wp, flowbox)
            flowbox.add(item)

        scrolled.add(flowbox)
        content.pack_start(scrolled, True, True, 0)

        self._current_picker = flowbox
        self._current_mode = current_mode
        mode_combo.connect("changed", lambda c: setattr(self, "_current_mode", c.get_active_id()))

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            selected = flowbox.get_selected_children()
            if selected:
                child = selected[0]
                wallpaper = child.get_child().get_child().wallpaper_data
                mode = mode_combo.get_active_id()
                self._assign_wallpaper(workspace, wallpaper, mode)

        dialog.destroy()

        dialog.destroy()

    def _create_picker_item(self, wp, flowbox: Gtk.FlowBox) -> Gtk.EventBox:
        event_box = Gtk.EventBox()
        event_box.set_property("width-request", 140)
        event_box.set_property("height-request", 120)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(wp["path"], 130, 80, True)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
        except Exception:
            image = Gtk.Image.new_from_icon_name("image-x-generic", Gtk.IconSize.DIALOG)

        vbox.pack_start(image, True, True, 0)

        label = Gtk.Label(label=wp["filename"])
        label.set_ellipsize(2)
        label.set_property("max-width-chars", 18)
        vbox.pack_start(label, False, False, 0)

        event_box.add(vbox)
        event_box.wallpaper_data = wp
        event_box.connect("button-press-event", self._on_picker_item_selected, flowbox)

        return event_box

    def _on_picker_item_selected(self, widget: Gtk.Widget, event: Gdk.Event, flowbox: Gtk.FlowBox) -> None:
        for child in flowbox.get_children():
            child.set_state_flags(Gtk.StateFlags.NORMAL, True)
        widget.set_state_flags(Gtk.StateFlags.SELECTED, True)
        self._current_selection = widget.wallpaper_data

    def _assign_wallpaper(self, workspace: int, wallpaper: dict, mode: str = "fill") -> None:
        conn = self._get_db_connection()
        conn.execute(
            "INSERT OR REPLACE INTO assignments(workspace, wallpaper_id, mode) VALUES(?, ?, ?)",
            (workspace, wallpaper["id"], mode),
        )
        conn.commit()
        conn.close()

        self._assignments[workspace] = {"wallpaper_id": wallpaper["id"], "mode": mode}
        self._populate_grid()
        self._save_state()
        self._status_label.set_text(f"Workspace {workspace}: {wallpaper['filename']} ({mode})")

    def _load_state(self) -> None:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
                    self._selected_workspace = state.get("last_workspace", 1)
            except (json.JSONDecodeError, IOError):
                self._selected_workspace = 1

    def _save_state(self) -> None:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        state = {"last_workspace": self._selected_workspace}
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)

    def _build_ui(self) -> None:
        self.window = Gtk.ApplicationWindow(application=self, title=__app_name__)
        self.window.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.window.set_resizable(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Gtk.Label()
        header.set_markup(f"<span weight='bold' size='large'>{__app_name__}</span>")
        header.set_property("halign", Gtk.Align.START)
        header.set_property("margin", 12)
        header.set_property("margin-bottom", 8)
        header.set_name("header")
        vbox.pack_start(header, False, False, 0)

        subheader = Gtk.Label()
        subheader.set_text("Click on a workspace to change its wallpaper")
        subheader.set_property("margin-left", 12)
        subheader.set_property("margin-bottom", 8)
        subheader.set_name("subheader")
        vbox.pack_start(subheader, False, False, 0)

        self._grid = Gtk.Grid()
        self._grid.set_column_spacing(8)
        self._grid.set_row_spacing(8)
        self._grid.set_property("margin", 12)
        vbox.pack_start(self._grid, True, True, 0)

        self._status_label = Gtk.Label()
        self._status_label.set_property("margin", 8)
        self._status_label.set_property("halign", Gtk.Align.CENTER)
        self._status_label.set_text("Select a workspace to change wallpaper")
        vbox.pack_start(self._status_label, False, False, 0)

        self.window.add(vbox)