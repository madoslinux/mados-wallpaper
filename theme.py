"""CSS theme for mados-wallpaper using Nord palette."""

from .config import NORD


def get_css() -> str:
    bg = NORD["polar_night"]["darkest"]
    bg_light = NORD["polar_night"]["darker"]
    fg = NORD["snow_storm"]["darkest"]
    fg_light = NORD["snow_storm"]["darker"]
    accent = NORD["frost"]["cyan"]
    hover = NORD["frost"]["teal"]

    return f"""
        window {{
            background-color: {bg};
            color: {fg};
            font-family: "Inter", "Sans Serif";
            font-size: 12px;
        }}

        .header {{
            background-color: {bg_light};
            padding: 12px;
            font-weight: bold;
            font-size: 14px;
        }}

        .wallpaper-grid {{
            padding: 8px;
        }}

        .wallpaper-item {{
            background-color: {bg_light};
            border-radius: 6px;
            padding: 4px;
            margin: 4px;
        }}

        .wallpaper-item:hover {{
            background-color: {hover};
        }}

        .wallpaper-item.selected {{
            border: 2px solid {accent};
        }}

        .wallpaper-image {{
            border-radius: 4px;
            background-color: {bg};
        }}

        .wallpaper-name {{
            padding: 4px;
            text-align: center;
        }}

        .btn {{
            background-color: {accent};
            color: {bg};
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
        }}

        .btn:hover {{
            background-color: {hover};
        }}

        .btn-box {{
            padding: 8px;
        }}

        scrollbar {{
            background-color: {bg};
            min-width: 8px;
        }}

        scrollbar slider {{
            background-color: {bg_light};
            border-radius: 4px;
        }}

        scrollbar slider:hover {{
            background-color: {accent};
        }}
    """