"""
HexFox brand tokens.

Colors and typography lifted straight from the hexfox.com brand kit
(docs/hexfox-brand-content) so this internal tool looks and feels
like a first-party HexFox product.
"""

import os

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

# ---------------------------------------------------------------------------
# Palette (from hexfox.com :root custom properties)
# ---------------------------------------------------------------------------
INK = "#0a0a0a"          # near-black, primary text / dark surfaces
INK_SOFT = "#151513"     # slightly lifted dark surface (cards on dark bg)
GRAPHITE = "#5b5b54"     # secondary text
GRAPH_M = "#3a3a35"      # tertiary text on light surfaces
WHITE = "#ffffff"
WHITE_2 = "#f5f5f5"
WHITE_3 = "#ebebeb"
LINE = "#0a0a0a"
LINE_SOFT = "#d4d4d0"
ORANGE = "#f27d00"       # primary brand accent
ORANGE_DARK = "#d46a00"
ORANGE_DEEP = "#c5520a"  # logo shadow tone
PEACH = "#ffd7ac"        # logo highlight tone
SUCCESS = "#2f9e58"
DANGER = "#d94848"

# Semantic aliases used across the UI
BG_APP = INK
BG_PANEL = "#111110"
BG_CARD = "#171715"
BG_CARD_HOVER = "#1d1d1a"
BORDER = "#2a2a26"
TEXT_PRIMARY = WHITE
TEXT_SECONDARY = "#b8b8b2"
TEXT_MUTED = "#7d7d76"
ACCENT = ORANGE
ACCENT_HOVER = ORANGE_DARK

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------
# Boldonse (display) + Montserrat (body) ship in assets/fonts and are loaded
# at runtime in app.py. JetBrains Mono isn't bundled (Apache-2.0, widely
# preinstalled) so we fall back through a sane monospace stack.
FONT_DISPLAY = "Boldonse"
FONT_BODY = "Montserrat"
FONT_MONO_CANDIDATES = ["JetBrains Mono", "Consolas", "Cascadia Mono", "Courier New"]

ICON_PATH = os.path.join(ASSETS_DIR, "icon.ico")
LOGO_MARK_PATH = os.path.join(ASSETS_DIR, "logo_mark.png")
LOGO_TEXT_WHITE_PATH = os.path.join(ASSETS_DIR, "logo_text_white.png")
FONT_BOLDONSE_PATH = os.path.join(ASSETS_DIR, "fonts", "Boldonse.ttf")
FONT_MONTSERRAT_PATH = os.path.join(ASSETS_DIR, "fonts", "Montserrat.ttf")
