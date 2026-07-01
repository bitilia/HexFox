"""
Best-effort loader for the bundled HexFox brand fonts (Boldonse, Montserrat).

Windows has no "load this .ttf just for my process" API exposed to Python,
so we use the GDI AddFontResourceExW trick with FR_PRIVATE, which makes the
font usable by this process (and this process only) without installing it
system-wide or requiring admin rights. On other platforms we simply skip
this - the app falls back to clean system fonts and still looks great.
"""

from __future__ import annotations

import ctypes
import platform
from . import theme

_loaded = {"boldonse": False, "montserrat": False}


def load_brand_fonts() -> dict:
    """Attempt to privately register the bundled brand fonts. Safe no-op on failure."""
    if platform.system() != "Windows":
        return dict(_loaded)

    FR_PRIVATE = 0x10
    try:
        gdi32 = ctypes.windll.gdi32
        for key, path in (("boldonse", theme.FONT_BOLDONSE_PATH), ("montserrat", theme.FONT_MONTSERRAT_PATH)):
            try:
                added = gdi32.AddFontResourceExW(str(path), FR_PRIVATE, 0)
                _loaded[key] = bool(added)
            except Exception:
                _loaded[key] = False
    except Exception:
        pass
    return dict(_loaded)


def display_font_family() -> str:
    return theme.FONT_DISPLAY if _loaded.get("boldonse") else "Segoe UI"


def mono_font_family() -> str:
    import tkinter.font as tkfont
    try:
        available = set(tkfont.families())
    except Exception:
        available = set()
    for candidate in theme.FONT_MONO_CANDIDATES:
        if candidate in available:
            return candidate
    return "Courier New"
