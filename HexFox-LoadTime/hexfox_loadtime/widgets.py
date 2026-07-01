"""Reusable CTk widgets styled with the HexFox brand kit."""

from __future__ import annotations

import customtkinter as ctk

from . import theme
from .utils import format_bytes, format_seconds, short_host


class SiteRow(ctk.CTkFrame):
    """One editable "site to test" entry (label + url + remove button)."""

    def __init__(self, master, index: int, mono_font, on_remove=None, removable=True, **kwargs):
        super().__init__(master, fg_color=theme.BG_CARD, corner_radius=8, **kwargs)
        self.index = index
        self._on_remove = on_remove
        self.mono_font = mono_font

        self.grid_columnconfigure(2, weight=2)
        self.grid_columnconfigure(1, weight=1)

        self.idx_label = ctk.CTkLabel(
            self, text=f"{index:02d}", font=ctk.CTkFont(family=mono_font, size=13, weight="bold"),
            text_color=theme.ACCENT, width=32,
        )
        self.idx_label.grid(row=0, column=0, padx=(14, 6), pady=12, sticky="w")

        self.label_entry = ctk.CTkEntry(
            self, placeholder_text="Label (optional)", fg_color=theme.BG_APP,
            border_color=theme.BORDER, border_width=1, font=ctk.CTkFont(family=mono_font, size=12),
        )
        self.label_entry.grid(row=0, column=1, padx=6, pady=12, sticky="ew")

        self.url_entry = ctk.CTkEntry(
            self, placeholder_text="https://example.com", fg_color=theme.BG_APP,
            border_color=theme.BORDER, border_width=1, font=ctk.CTkFont(family=mono_font, size=12),
        )
        self.url_entry.grid(row=0, column=2, padx=6, pady=12, sticky="ew")

        self.remove_btn = ctk.CTkButton(
            self, text="✕", width=32, height=28, fg_color="transparent", hover_color=theme.BG_CARD_HOVER,
            text_color=theme.TEXT_MUTED, font=ctk.CTkFont(family=mono_font, size=13),
            command=self._remove,
        )
        self.remove_btn.grid(row=0, column=3, padx=(6, 14), pady=12, sticky="e")
        self.set_removable(removable)

    def set_removable(self, removable: bool):
        self.remove_btn.configure(state="normal" if removable else "disabled",
                                   text_color=theme.TEXT_MUTED if removable else theme.BORDER)

    def set_index(self, index: int):
        self.index = index
        self.idx_label.configure(text=f"{index:02d}")

    def _remove(self):
        if self._on_remove:
            self._on_remove(self)

    def get_values(self):
        return self.label_entry.get().strip(), self.url_entry.get().strip()

    def set_state(self, state: str):
        self.label_entry.configure(state=state)
        self.url_entry.configure(state=state)


class StatBlock(ctk.CTkFrame):
    """Big number + caption, e.g. TIME TO FIRST LOAD 0.84s"""

    def __init__(self, master, title: str, mono_font, accent=theme.ACCENT, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(family=mono_font, size=11, weight="bold"),
                     text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w")
        self.value_label = ctk.CTkLabel(self, text="—", font=ctk.CTkFont(family=mono_font, size=30, weight="bold"),
                                         text_color=accent, anchor="w")
        self.value_label.pack(anchor="w", pady=(2, 0))
        self.sub_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(family=mono_font, size=10),
                                       text_color=theme.TEXT_SECONDARY, anchor="w")
        self.sub_label.pack(anchor="w")

    def set(self, value_text: str, sub_text: str = ""):
        self.value_label.configure(text=value_text)
        self.sub_label.configure(text=sub_text)


class SiteResultCard(ctk.CTkFrame):
    """Aggregated result panel for a single tested site."""

    def __init__(self, master, mono_font, **kwargs):
        super().__init__(master, fg_color=theme.BG_CARD, corner_radius=10, border_width=1,
                          border_color=theme.BORDER, **kwargs)
        self.mono_font = mono_font

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(16, 4))
        self.title_label = ctk.CTkLabel(header, text="—", font=ctk.CTkFont(family=mono_font, size=14, weight="bold"),
                                         text_color=theme.TEXT_PRIMARY, anchor="w")
        self.title_label.pack(side="left")
        self.badge = ctk.CTkLabel(header, text="PENDING", font=ctk.CTkFont(family=mono_font, size=10, weight="bold"),
                                   text_color=theme.INK, fg_color=theme.TEXT_MUTED, corner_radius=4,
                                   padx=8, pady=2)
        self.badge.pack(side="right")

        self.url_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(family=mono_font, size=10),
                                       text_color=theme.TEXT_MUTED, anchor="w")
        self.url_label.pack(fill="x", padx=18, pady=(0, 12))

        stats_row = ctk.CTkFrame(self, fg_color="transparent")
        stats_row.pack(fill="x", padx=18, pady=(0, 10))
        stats_row.grid_columnconfigure((0, 1), weight=1)

        self.first_load_stat = StatBlock(stats_row, "TIME TO FIRST LOAD", mono_font, accent=theme.ACCENT)
        self.first_load_stat.grid(row=0, column=0, sticky="w", padx=(0, 10))

        self.all_elements_stat = StatBlock(stats_row, "TIME TO LOAD ALL ELEMENTS", mono_font, accent=theme.PEACH)
        self.all_elements_stat.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.detail_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(family=mono_font, size=11),
                                          text_color=theme.TEXT_SECONDARY, anchor="w", justify="left")
        self.detail_label.pack(fill="x", padx=18, pady=(2, 16))

    def set_pending(self, label: str, url: str):
        self.title_label.configure(text=label or short_host(url))
        self.url_label.configure(text=url)
        self.badge.configure(text="RUNNING…", fg_color=theme.ACCENT, text_color=theme.INK)
        self.first_load_stat.set("—")
        self.all_elements_stat.set("—")
        self.detail_label.configure(text="Testing in progress…")

    def set_summary(self, summary):
        self.title_label.configure(text=summary.label or short_host(summary.url))
        self.url_label.configure(text=summary.url)

        if not summary.ok:
            self.badge.configure(text="FAILED", fg_color=theme.DANGER, text_color=theme.WHITE)
            self.first_load_stat.set("—")
            self.all_elements_stat.set("—")
            err = summary.runs[-1].error if summary.runs else "Unknown error"
            self.detail_label.configure(text=f"Error: {err}", text_color=theme.DANGER)
            return

        self.badge.configure(text="DONE", fg_color=theme.SUCCESS, text_color=theme.WHITE)
        trials = len(summary.runs)
        successful = [r for r in summary.runs if r.ok]

        fl_vals = [r.time_to_first_load for r in successful]
        ae_vals = [r.time_to_all_elements for r in successful]

        self.first_load_stat.set(
            format_seconds(summary.median_first_load),
            f"range {format_seconds(min(fl_vals))}–{format_seconds(max(fl_vals))}" if len(fl_vals) > 1 else "median",
        )
        self.all_elements_stat.set(
            format_seconds(summary.median_all_elements),
            f"range {format_seconds(min(ae_vals))}–{format_seconds(max(ae_vals))}" if len(ae_vals) > 1 else "median",
        )

        avg_res = summary.avg_resource_count or 0
        avg_bytes = summary.avg_total_bytes or 0
        avg_failed = summary.avg_failed_count or 0
        ttfb = summary.median_ttfb or 0
        self.detail_label.configure(
            text=(f"TTFB {format_seconds(ttfb)}  ·  ~{avg_res:.0f} resources  ·  "
                  f"~{format_bytes(avg_bytes)} transferred  ·  "
                  f"{avg_failed:.0f} failed  ·  {trials} trial{'s' if trials != 1 else ''}"),
            text_color=theme.TEXT_SECONDARY,
        )
