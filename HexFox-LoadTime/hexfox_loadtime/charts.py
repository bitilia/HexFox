"""A small, dependency-free grouped bar chart for comparing sites."""

from __future__ import annotations

import tkinter as tk
import customtkinter as ctk

from . import theme


class ComparisonChart(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=theme.BG_CARD, corner_radius=10, **kwargs)
        self._data = []  # list of dicts: label, first_load, all_elements, fastest
        self._mono = "Courier New"

        self.canvas = tk.Canvas(self, bg=theme.BG_CARD, highlightthickness=0, height=260)
        self.canvas.pack(fill="both", expand=True, padx=16, pady=16)
        self.canvas.bind("<Configure>", lambda e: self._redraw())

        legend = ctk.CTkFrame(self, fg_color="transparent")
        legend.pack(fill="x", padx=16, pady=(0, 14))
        self._legend_dot(legend, theme.ACCENT, "Time to First Load")
        self._legend_dot(legend, theme.PEACH, "Time to Load All Elements", pad=(24, 0))

    def _legend_dot(self, parent, color, text, pad=(0, 0)):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(side="left", padx=pad)
        dot = tk.Canvas(wrap, width=10, height=10, bg=theme.BG_CARD, highlightthickness=0)
        dot.pack(side="left", padx=(0, 6))
        dot.create_oval(1, 1, 9, 9, fill=color, outline="")
        ctk.CTkLabel(wrap, text=text, font=ctk.CTkFont(family=self._mono, size=11),
                     text_color=theme.TEXT_SECONDARY).pack(side="left")

    def set_mono_font(self, family: str):
        self._mono = family

    def set_data(self, rows: list):
        """rows: list of dicts with keys label, first_load, all_elements"""
        self._data = rows
        self._redraw()

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        if not self._data:
            c.create_text(20, 20, anchor="nw", text="Run a comparison to see results here.",
                           fill=theme.TEXT_MUTED, font=(self._mono, 11))
            return

        width = max(c.winfo_width(), 200)
        height = max(c.winfo_height(), 200)
        left_pad = 130
        right_pad = 30
        top_pad = 10
        bottom_pad = 30
        row_h = max(34, (height - top_pad - bottom_pad) // max(1, len(self._data)))

        max_val = max([max(r["first_load"], r["all_elements"]) for r in self._data] + [0.001])
        plot_w = width - left_pad - right_pad

        fastest_idx = min(range(len(self._data)), key=lambda i: self._data[i]["all_elements"]) if self._data else None

        for i, row in enumerate(self._data):
            y0 = top_pad + i * row_h
            bar_h = min(12, row_h // 3)
            label = row["label"]
            if len(label) > 20:
                label = label[:19] + "…"
            c.create_text(left_pad - 12, y0 + row_h / 2, anchor="e", text=label,
                           fill=theme.TEXT_PRIMARY, font=(self._mono, 11))

            fl_w = (row["first_load"] / max_val) * plot_w
            ae_w = (row["all_elements"] / max_val) * plot_w

            y_fl = y0 + row_h / 2 - bar_h - 3
            y_ae = y0 + row_h / 2 + 3

            c.create_rectangle(left_pad, y_fl, left_pad + max(2, fl_w), y_fl + bar_h,
                                fill=theme.ACCENT, outline="")
            c.create_text(left_pad + max(2, fl_w) + 8, y_fl + bar_h / 2, anchor="w",
                           text=f"{row['first_load']:.2f}s", fill=theme.ACCENT, font=(self._mono, 10))

            c.create_rectangle(left_pad, y_ae, left_pad + max(2, ae_w), y_ae + bar_h,
                                fill=theme.PEACH, outline="")
            c.create_text(left_pad + max(2, ae_w) + 8, y_ae + bar_h / 2, anchor="w",
                           text=f"{row['all_elements']:.2f}s", fill=theme.PEACH, font=(self._mono, 10))

            if i == fastest_idx and len(self._data) > 1:
                c.create_text(left_pad, y0 + row_h - 6, anchor="w", text="★ FASTEST OVERALL",
                              fill=theme.SUCCESS, font=(self._mono, 9, "bold"))

            if i > 0:
                c.create_line(left_pad - 12, y0, width - right_pad, y0, fill=theme.BORDER)
