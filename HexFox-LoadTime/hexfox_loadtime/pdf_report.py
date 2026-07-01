"""
PDF report generation for the HexFox Load Time Comparator.

Produces a clean, print-friendly report of a comparison run: test settings,
a card-style section per site (raw + total timing, TTFB, connection setup,
resource/byte counts), and -- for multi-site runs -- a stacked-bar
comparison chart plus a summary table.

Branding is optional: when disabled, the report drops the HexFox logo,
brand colors, and display font in favor of a neutral black/grey palette
and standard PDF fonts, so the same report can be shared without company
branding when that's preferred.
"""

from __future__ import annotations

import os
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable, HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from . import theme
from .utils import format_bytes, format_seconds, short_host

_FONTS_REGISTERED = False


def _register_fonts() -> bool:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return True
    try:
        pdfmetrics.registerFont(TTFont("Boldonse", theme.FONT_BOLDONSE_PATH))
        pdfmetrics.registerFont(TTFont("Montserrat", theme.FONT_MONTSERRAT_PATH))
        _FONTS_REGISTERED = True
    except Exception:
        _FONTS_REGISTERED = False
    return _FONTS_REGISTERED


def _c(hex_value: str):
    return colors.HexColor(hex_value)


class _Palette:
    """Resolved colors + fonts for either the branded or neutral report style."""

    def __init__(self, branded: bool):
        self.branded = branded
        if branded and _register_fonts():
            self.font_title = "Boldonse"
            self.font_body = "Montserrat"
            self.font_body_bold = "Montserrat"
        else:
            self.font_title = "Helvetica-Bold"
            self.font_body = "Helvetica"
            self.font_body_bold = "Helvetica-Bold"

        if branded:
            self.ink = _c(theme.INK)
            self.accent = _c(theme.ORANGE)
            self.secondary = _c(theme.ORANGE_DEEP)
            self.muted = _c(theme.GRAPHITE)
            self.line = _c(theme.LINE_SOFT)
            self.panel_bg = _c(theme.WHITE_2)
        else:
            self.ink = _c("#161616")
            self.accent = _c("#37474F")
            self.secondary = _c("#90A4AE")
            self.muted = _c("#6b6b6b")
            self.line = _c("#dcdcdc")
            self.panel_bg = _c("#f4f4f4")

        self.success = _c(theme.SUCCESS)
        self.danger = _c(theme.DANGER)
        self.success_hex = theme.SUCCESS.lstrip("#")
        self.danger_hex = theme.DANGER.lstrip("#")
        self.white = _c("#ffffff")


class _ComparisonBars(Flowable):
    """Stacked horizontal bars: [connection][raw metric], mirroring the
    in-app comparison chart, redrawn natively for the PDF (no rasterization
    of the Tkinter canvas involved)."""

    ROW_HEIGHT = 34
    BAR_HEIGHT = 8

    def __init__(self, rows: list, width: float, palette: _Palette):
        super().__init__()
        self.rows = rows
        self.width = width
        self.palette = palette
        self.height = max(1, len(rows)) * self.ROW_HEIGHT + 10

    def draw(self):
        c = self.canv
        p = self.palette
        left_pad = 118
        right_pad = 8
        plot_w = max(10.0, self.width - left_pad - right_pad)
        max_val = max(
            [max(r["connect_time"] + r["raw_first_load"], r["connect_time"] + r["raw_all_elements"])
             for r in self.rows] + [0.001]
        )

        for i, row in enumerate(self.rows):
            row_top = self.height - i * self.ROW_HEIGHT
            label = row["label"]
            if len(label) > 20:
                label = label[:19] + "…"
            c.setFont(p.font_body, 8)
            c.setFillColor(p.ink)
            c.drawRightString(left_pad - 8, row_top - self.ROW_HEIGHT / 2 - 2, label)

            connect_w = (row["connect_time"] / max_val) * plot_w
            fl_w = max(1.0, (row["raw_first_load"] / max_val) * plot_w)
            ae_w = max(1.0, (row["raw_all_elements"] / max_val) * plot_w)

            y_fl = row_top - self.BAR_HEIGHT - 3
            y_ae = row_top - self.BAR_HEIGHT * 2 - 8

            if connect_w > 0.5:
                c.setFillColor(p.muted)
                c.rect(left_pad, y_fl, connect_w, self.BAR_HEIGHT, fill=1, stroke=0)
                c.rect(left_pad, y_ae, connect_w, self.BAR_HEIGHT, fill=1, stroke=0)

            c.setFillColor(p.accent)
            c.rect(left_pad + connect_w, y_fl, fl_w, self.BAR_HEIGHT, fill=1, stroke=0)
            c.setFillColor(p.secondary)
            c.rect(left_pad + connect_w, y_ae, ae_w, self.BAR_HEIGHT, fill=1, stroke=0)

            c.setFont(p.font_body, 7)
            c.setFillColor(p.accent)
            c.drawString(left_pad + connect_w + fl_w + 4, y_fl + 2, f"{row['raw_first_load']:.2f}s raw")
            c.setFillColor(p.secondary)
            c.drawString(left_pad + connect_w + ae_w + 4, y_ae + 2, f"{row['raw_all_elements']:.2f}s raw")

            if i > 0:
                c.setStrokeColor(p.line)
                c.setLineWidth(0.5)
                c.line(left_pad - 8, row_top, self.width, row_top)


def _stat_table(site: dict, palette: _Palette) -> Table:
    p = palette
    label_style = ParagraphStyle("StatLabel", fontName=p.font_body_bold, fontSize=8, leading=11, textColor=p.muted)
    accent_value_style = ParagraphStyle("StatValueAccent", fontName=p.font_title, fontSize=17, leading=21,
                                         textColor=p.accent)
    secondary_value_style = ParagraphStyle("StatValueSecondary", fontName=p.font_title, fontSize=17, leading=21,
                                            textColor=p.secondary)
    total_style = ParagraphStyle("StatTotal", fontName=p.font_body, fontSize=8, leading=11, textColor=p.muted)

    data = [
        [Paragraph("TIME TO FIRST LOAD", label_style), Paragraph("TIME TO LOAD ALL ELEMENTS", label_style)],
        [
            Paragraph(f"{format_seconds(site['raw_first_load'])}  (raw)", accent_value_style),
            Paragraph(f"{format_seconds(site['raw_all_elements'])}  (raw)", secondary_value_style),
        ],
        [
            Paragraph(f"total incl. connection: {format_seconds(site['total_first_load'])}", total_style),
            Paragraph(f"total incl. connection: {format_seconds(site['total_all_elements'])}", total_style),
        ],
    ]
    table = Table(data, colWidths=[240, 240])
    table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _site_block(site: dict, palette: _Palette, body_style, small_muted_style) -> KeepTogether:
    p = palette
    flow = []

    title = site["label"] or short_host(site["url"])
    status = "DONE" if site["ok"] else "FAILED"
    status_color = p.success_hex if site["ok"] else p.danger_hex

    header_table = Table(
        [[Paragraph(f"<font name='{p.font_body_bold}' size=11.5>{title}</font>", body_style),
          Paragraph(f"<font name='{p.font_body_bold}' size=8 color='#{status_color}'>{status}</font>", body_style)]],
        colWidths=[420, 60],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    flow.append(header_table)
    flow.append(Paragraph(site["url"], small_muted_style))
    flow.append(Spacer(1, 6))

    if not site["ok"]:
        err = site.get("error") or "Unknown error"
        flow.append(Paragraph(f"<font color='#{status_color}'>Error: {err}</font>", body_style))
    else:
        flow.append(_stat_table(site, palette))
        flow.append(Spacer(1, 4))
        detail = (
            f"TTFB {format_seconds(site['ttfb'])}  ·  connection setup {format_seconds(site['connect_time'])}  ·  "
            f"~{site['avg_resource_count']:.0f} resources  ·  ~{format_bytes(site['avg_total_bytes'])} transferred  ·  "
            f"{site['avg_failed_count']:.0f} failed  ·  {site['trials']} trial{'s' if site['trials'] != 1 else ''}"
        )
        flow.append(Paragraph(detail, small_muted_style))

    flow.append(Spacer(1, 4))
    flow.append(HRFlowable(width="100%", color=p.line, thickness=0.75))
    flow.append(Spacer(1, 10))
    return KeepTogether(flow)


def _comparison_table(sites: list, palette: _Palette, available_width: float) -> Table:
    p = palette
    header_style = ParagraphStyle("CompHeader", fontName=p.font_body_bold, fontSize=7.5, leading=10, textColor=p.white)
    header = [Paragraph(t, header_style) for t in
              ["Site", "1st load\n(raw)", "1st load\n(total)", "All elements\n(raw)", "All elements\n(total)",
               "Resources", "Size", "Failed"]]
    data = [header]
    for s in sites:
        if not s["ok"]:
            data.append([s["label"] or short_host(s["url"]), "—", "—", "—", "—", "—", "—", "—"])
            continue
        data.append([
            s["label"] or short_host(s["url"]),
            format_seconds(s["raw_first_load"]),
            format_seconds(s["total_first_load"]),
            format_seconds(s["raw_all_elements"]),
            format_seconds(s["total_all_elements"]),
            f"{s['avg_resource_count']:.0f}",
            format_bytes(s["avg_total_bytes"]),
            f"{s['avg_failed_count']:.0f}",
        ])

    weights = [0.20, 0.115, 0.115, 0.135, 0.135, 0.105, 0.105, 0.09]
    col_widths = [available_width * w for w in weights]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("FONTNAME", (0, 1), (-1, -1), p.font_body),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), p.accent),
        ("TEXTCOLOR", (0, 1), (-1, -1), p.ink),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [p.white, p.panel_bg]),
        ("GRID", (0, 0), (-1, -1), 0.5, p.line),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
    ]
    table.setStyle(TableStyle(style))
    return table


def build_pdf(path: str, run_meta: dict, site_rows: list, include_branding: bool = True) -> None:
    """Write a comparison report PDF to `path`.

    run_meta: dict with keys generated_at, trials, device_label, network_label,
              network_description, cpu_label.
    site_rows: list of dicts (see app.py's `_site_export_row`) - one per tested site.
    """
    palette = _Palette(include_branding)
    p = palette

    doc = SimpleDocTemplate(
        path, pagesize=letter,
        topMargin=20 * mm, bottomMargin=16 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title="HexFox Load Time Report" if include_branding else "Website Load Time Report",
        author="HexFox Load Time Comparator",
    )

    title_style = ParagraphStyle("Title", fontName=p.font_title, fontSize=20, textColor=p.ink, leading=24)
    tagline_style = ParagraphStyle("Tagline", fontName=p.font_body_bold, fontSize=9, textColor=p.accent,
                                    leading=12, spaceAfter=2)
    meta_style = ParagraphStyle("Meta", fontName=p.font_body, fontSize=8.5, textColor=p.muted, leading=12)
    h2_style = ParagraphStyle("H2", fontName=p.font_title, fontSize=13, textColor=p.ink,
                               spaceBefore=6, spaceAfter=8)
    body_style = ParagraphStyle("Body", fontName=p.font_body, fontSize=9.5, textColor=p.ink, leading=13)
    small_muted_style = ParagraphStyle("SmallMuted", fontName=p.font_body, fontSize=8, textColor=p.muted, leading=11)
    settings_label_style = ParagraphStyle("SettingsLabel", fontName=p.font_body_bold, fontSize=8.5,
                                           textColor=p.muted, leading=12)
    settings_value_style = ParagraphStyle("SettingsValue", fontName=p.font_body, fontSize=8.5,
                                           textColor=p.ink, leading=12)

    story = []

    if include_branding:
        try:
            logo_path = os.path.join(theme.ASSETS_DIR, "logo_text_dark.png")
            logo = Image(logo_path, width=120, height=120 * (338 / 1400))
            story.append(logo)
        except Exception:
            story.append(Paragraph("HEXFOX", title_style))
        story.append(Spacer(1, 6))
        story.append(Paragraph("LOAD TIME COMPARATOR — REPORT", tagline_style))
    else:
        story.append(Paragraph("Website Load Time Report", title_style))

    story.append(Paragraph(f"Generated {run_meta['generated_at']}", meta_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", color=p.line, thickness=1))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Test Settings", h2_style))
    settings_data = [
        [Paragraph("Trials per site", settings_label_style), Paragraph(str(run_meta["trials"]), settings_value_style)],
        [Paragraph("Simulated device", settings_label_style), Paragraph(run_meta["device_label"], settings_value_style)],
        [Paragraph("Network throttle", settings_label_style),
         Paragraph(f"{run_meta['network_label']} — {run_meta['network_description']}", settings_value_style)],
        [Paragraph("CPU throttle", settings_label_style), Paragraph(run_meta["cpu_label"], settings_value_style)],
    ]
    settings_table = Table(settings_data, colWidths=[110, 360])
    settings_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(settings_table)
    story.append(Spacer(1, 18))

    story.append(Paragraph("Results", h2_style))
    for site in site_rows:
        story.append(_site_block(site, palette, body_style, small_muted_style))

    successful = [s for s in site_rows if s["ok"]]
    if len(successful) > 1:
        story.append(Spacer(1, 4))
        story.append(Paragraph("Comparison", h2_style))
        chart_rows = [
            {"label": s["label"] or short_host(s["url"]), "connect_time": s["connect_time"],
             "raw_first_load": s["raw_first_load"], "raw_all_elements": s["raw_all_elements"]}
            for s in successful
        ]
        available_width = doc.width
        story.append(_ComparisonBars(chart_rows, available_width, palette))
        story.append(Spacer(1, 14))
        story.append(_comparison_table(site_rows, palette, available_width))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", color=p.line, thickness=0.75))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Methodology: measured with plain HTTP requests (no browser/JS execution). \"Raw\" figures have "
        "connection setup (DNS+TCP+TLS, plus any simulated network latency) subtracted out, isolating the "
        "HTML/asset transfer itself. \"Total\" figures include that connection overhead. "
        "Network/CPU throttling above (if any) simulate slower conditions; see the app README for exact figures.",
        small_muted_style,
    ))

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont(p.font_body, 7.5)
        canvas.setFillColor(p.muted)
        footer_text = "HexFox Labs — Internal Tooling" if include_branding else "Website Load Time Report"
        canvas.drawString(18 * mm, 10 * mm, footer_text)
        canvas.drawRightString(letter[0] - 18 * mm, 10 * mm, f"Page {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
