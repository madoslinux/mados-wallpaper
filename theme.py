"""CSS theme for mados-wallpaper using Nord palette."""

from config import NORD


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
            font-size: 16px;
            color: {fg_light};
        }}

        .subheader {{
            color: {fg};
            font-size: 12px;
            opacity: 0.7;
        }}

        .workspace-label {{
            color: {accent};
            font-size: 12px;
        }}

        .wallpaper-thumb {{
            border-radius: 6px;
            background-color: {bg};
        }}

        .wallpaper-filename {{
            color: {fg_light};
            font-size: 10px;
        }}

        GtkGrid {{
            background-color: {bg};
        }}

        GtkEventBox {{
            background-color: {bg_light};
            border-radius: 8px;
        }}

        GtkEventBox:hover {{
            background-color: {hover};
        }}

        button {{
            background-color: {accent};
            color: {bg};
            border: none;
            border-radius: 6px;
            padding: 10px 16px;
            font-weight: bold;
        }}

        button:hover {{
            background-color: {hover};
        }}

        scrollbar {{
            background-color: {bg};
            min-width: 10px;
        }}

        scrollbar slider {{
            background-color: {bg_light};
            border-radius: 5px;
        }}

        scrollbar slider:hover {{
            background-color: {accent};
        }}
    """