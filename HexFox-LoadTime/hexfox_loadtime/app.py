"""
HexFox Load Time Comparator
============================
A local desktop tool for comparing website loading performance.

Measures, per URL:
  - TIME TO FIRST LOAD          how long until the initial HTML document arrives
  - TIME TO LOAD ALL ELEMENTS   how long until every discoverable resource
                                 (images, CSS, JS, fonts, ...) finishes downloading

See hexfox_loadtime/network.py for full methodology + limitations.
"""

from __future__ import annotations

import csv
import queue
import threading
from datetime import datetime

import customtkinter as ctk
from PIL import Image

from . import theme, fonts
from .network import LoadTimeTester, SiteTestSummary
from .charts import ComparisonChart
from .throttle import NETWORK_PRESETS, CPU_PRESETS
from .utils import normalize_url, format_seconds, short_host
from .widgets import SiteRow, SiteResultCard
from . import pdf_report

ctk.set_appearance_mode("dark")

USER_AGENTS = {
    "Desktop · Chrome": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 HexFoxLoadTime/1.0"
    ),
    "Mobile · Safari": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1 HexFoxLoadTime/1.0"
    ),
}


class HexFoxApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        fonts.load_brand_fonts()
        self.mono = fonts.mono_font_family()
        self.display = fonts.display_font_family()

        self.title("HexFox — Load Time Comparator")
        self.geometry("1180x840")
        self.minsize(980, 680)
        self.configure(fg_color=theme.BG_APP)
        try:
            self.iconbitmap(theme.ICON_PATH)
        except Exception:
            pass

        self._events: "queue.Queue[dict]" = queue.Queue()
        self._stop_event = threading.Event()
        self._worker = None
        self._running = False
        self._site_rows = []
        self._result_cards = {}
        self._summaries = {}
        self._run_order = []
        self._log_tags = set()
        self._last_network_label = "No throttling"
        self._last_network_description = NETWORK_PRESETS["No throttling"].description
        self._last_cpu_label = "No throttling"
        self._last_trials = 3
        self._last_device_label = "Desktop · Chrome"

        self._build_header()
        self._build_body()
        self._poll_events()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=theme.INK, corner_radius=0, height=84)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=24, pady=14)

        try:
            logo_img = Image.open(theme.LOGO_MARK_PATH)
            self._logo_ctk_image = ctk.CTkImage(light_image=logo_img, dark_image=logo_img, size=(40, 40))
            ctk.CTkLabel(left, image=self._logo_ctk_image, text="").pack(side="left", padx=(0, 12))
        except Exception:
            pass

        title_wrap = ctk.CTkFrame(left, fg_color="transparent")
        title_wrap.pack(side="left")
        ctk.CTkLabel(title_wrap, text="HEXFOX", font=ctk.CTkFont(family=self.display, size=20),
                     text_color=theme.WHITE, anchor="w").pack(anchor="w")
        ctk.CTkLabel(title_wrap, text="LOAD TIME COMPARATOR",
                     font=ctk.CTkFont(family=self.mono, size=11, weight="bold"),
                     text_color=theme.ORANGE, anchor="w").pack(anchor="w")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", padx=24, pady=14)
        ctk.CTkLabel(right, text="LOCAL TOOL", font=ctk.CTkFont(family=self.mono, size=10, weight="bold"),
                     text_color=theme.INK, fg_color=theme.ORANGE, corner_radius=4, padx=10, pady=4).pack(side="right")

        rule = ctk.CTkFrame(self, fg_color=theme.ORANGE, height=2, corner_radius=0)
        rule.pack(fill="x", side="top")

    def _build_body(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_APP)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1)
        content = ctk.CTkFrame(scroll, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=28, pady=24)

        self._build_targets_section(content)
        self._build_settings_section(content)
        self._build_controls_section(content)
        self._build_log_section(content)
        self._build_results_section(content)

    def _section_title(self, parent, index: str, text: str):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", pady=(24, 10))
        ctk.CTkLabel(wrap, text=index, font=ctk.CTkFont(family=self.mono, size=12, weight="bold"),
                     text_color=theme.ORANGE).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(wrap, text=text, font=ctk.CTkFont(family=self.display, size=15),
                     text_color=theme.WHITE).pack(side="left")
        line = ctk.CTkFrame(wrap, fg_color=theme.BORDER, height=1)
        line.pack(side="left", fill="x", expand=True, padx=(16, 0))
        return wrap

    def _build_targets_section(self, parent):
        self._section_title(parent, "01", "WEBSITES TO TEST")
        self.targets_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.targets_frame.pack(fill="x")

        self.rows_container = ctk.CTkFrame(self.targets_frame, fg_color="transparent")
        self.rows_container.pack(fill="x")

        self._add_site_row()

        add_btn = ctk.CTkButton(
            self.targets_frame, text="+  ADD SITE TO COMPARE", fg_color="transparent",
            hover_color=theme.BG_CARD_HOVER, border_width=1, border_color=theme.BORDER,
            text_color=theme.TEXT_SECONDARY, font=ctk.CTkFont(family=self.mono, size=11, weight="bold"),
            height=34, command=self._add_site_row,
        )
        add_btn.pack(fill="x", pady=(8, 0))

    def _add_site_row(self):
        row = SiteRow(self.rows_container, index=len(self._site_rows) + 1, mono_font=self.mono,
                      on_remove=self._remove_site_row)
        row.pack(fill="x", pady=4)
        self._site_rows.append(row)
        self._refresh_row_removability()

    def _remove_site_row(self, row):
        if len(self._site_rows) <= 1:
            return
        self._site_rows.remove(row)
        row.destroy()
        for i, r in enumerate(self._site_rows, start=1):
            r.set_index(i)
        self._refresh_row_removability()

    def _refresh_row_removability(self):
        removable = len(self._site_rows) > 1
        for r in self._site_rows:
            r.set_removable(removable)

    def _build_settings_section(self, parent):
        self._section_title(parent, "02", "TEST SETTINGS")
        panel = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=10)
        panel.pack(fill="x")

        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=16)

        self.trials_var = ctk.StringVar(value="3")
        self._labeled_segment(row, "TRIALS PER SITE", ["1", "3", "5"], self.trials_var)

        self.device_var = ctk.StringVar(value="Desktop · Chrome")
        self._labeled_segment(row, "SIMULATED DEVICE", list(USER_AGENTS.keys()), self.device_var)

        throttle_row = ctk.CTkFrame(panel, fg_color="transparent")
        throttle_row.pack(fill="x", padx=18, pady=(0, 16))

        self.network_var = ctk.StringVar(value="No throttling")
        self._labeled_segment(throttle_row, "NETWORK THROTTLE", list(NETWORK_PRESETS.keys()), self.network_var)

        self.cpu_var = ctk.StringVar(value="No throttling")
        self._labeled_segment(throttle_row, "CPU THROTTLE", list(CPU_PRESETS.keys()), self.cpu_var)

        adv = ctk.CTkFrame(panel, fg_color="transparent")
        adv.pack(fill="x", padx=18, pady=(0, 16))

        self.timeout_entry = self._labeled_entry(adv, "TIMEOUT (s)", "15")
        self.concurrency_entry = self._labeled_entry(adv, "CONCURRENCY", "8")

        self.parse_css_var = ctk.BooleanVar(value=True)
        cb_wrap = ctk.CTkFrame(adv, fg_color="transparent")
        cb_wrap.pack(side="left", padx=(24, 0))
        ctk.CTkLabel(cb_wrap, text="INCLUDE CSS-REFERENCED ASSETS", font=ctk.CTkFont(family=self.mono, size=10, weight="bold"),
                     text_color=theme.TEXT_MUTED).pack(anchor="w")
        ctk.CTkCheckBox(cb_wrap, text="fonts & images inside stylesheets", variable=self.parse_css_var,
                         font=ctk.CTkFont(family=self.mono, size=11), fg_color=theme.ORANGE,
                         hover_color=theme.ORANGE_DARK, text_color=theme.TEXT_SECONDARY,
                         checkmark_color=theme.INK).pack(anchor="w", pady=(4, 0))

    def _labeled_segment(self, parent, label, values, variable):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(side="left", padx=(0, 32))
        ctk.CTkLabel(wrap, text=label, font=ctk.CTkFont(family=self.mono, size=10, weight="bold"),
                     text_color=theme.TEXT_MUTED).pack(anchor="w")
        seg = ctk.CTkSegmentedButton(wrap, values=values, variable=variable,
                                      font=ctk.CTkFont(family=self.mono, size=11),
                                      fg_color=theme.BG_APP, selected_color=theme.ORANGE,
                                      selected_hover_color=theme.ORANGE_DARK, unselected_color=theme.BG_APP,
                                      text_color=theme.TEXT_SECONDARY, text_color_disabled=theme.TEXT_MUTED)
        seg.pack(anchor="w", pady=(4, 0))
        return seg

    def _labeled_entry(self, parent, label, default):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(wrap, text=label, font=ctk.CTkFont(family=self.mono, size=10, weight="bold"),
                     text_color=theme.TEXT_MUTED).pack(anchor="w")
        entry = ctk.CTkEntry(wrap, width=90, fg_color=theme.BG_APP, border_color=theme.BORDER,
                              font=ctk.CTkFont(family=self.mono, size=12))
        entry.insert(0, default)
        entry.pack(anchor="w", pady=(4, 0))
        return entry

    def _build_controls_section(self, parent):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", pady=(24, 0))

        self.run_btn = ctk.CTkButton(
            wrap, text="▶  RUN COMPARISON", height=42, corner_radius=6, fg_color=theme.ORANGE,
            hover_color=theme.ORANGE_DARK, text_color=theme.INK,
            font=ctk.CTkFont(family=self.mono, size=13, weight="bold"), command=self._start_run,
        )
        self.run_btn.pack(side="left")

        self.stop_btn = ctk.CTkButton(
            wrap, text="■  STOP", height=42, width=110, corner_radius=6, fg_color="transparent",
            border_width=1, border_color=theme.DANGER, hover_color=theme.BG_CARD_HOVER, text_color=theme.DANGER,
            font=ctk.CTkFont(family=self.mono, size=13, weight="bold"), command=self._stop_run, state="disabled",
        )
        self.stop_btn.pack(side="left", padx=(10, 0))

        self.export_csv_btn = ctk.CTkButton(
            wrap, text="⇩  EXPORT CSV", height=42, width=140, corner_radius=6, fg_color="transparent",
            border_width=1, border_color=theme.BORDER, hover_color=theme.BG_CARD_HOVER, text_color=theme.TEXT_SECONDARY,
            font=ctk.CTkFont(family=self.mono, size=13, weight="bold"), command=self._export_csv, state="disabled",
        )
        self.export_csv_btn.pack(side="left", padx=(10, 0))

        self.export_pdf_btn = ctk.CTkButton(
            wrap, text="⇩  EXPORT PDF", height=42, width=140, corner_radius=6, fg_color="transparent",
            border_width=1, border_color=theme.BORDER, hover_color=theme.BG_CARD_HOVER, text_color=theme.TEXT_SECONDARY,
            font=ctk.CTkFont(family=self.mono, size=13, weight="bold"), command=self._export_pdf, state="disabled",
        )
        self.export_pdf_btn.pack(side="left", padx=(10, 0))

        self.status_label = ctk.CTkLabel(wrap, text="Ready.", font=ctk.CTkFont(family=self.mono, size=11),
                                          text_color=theme.TEXT_MUTED)
        self.status_label.pack(side="left", padx=(20, 0))

        options_row = ctk.CTkFrame(parent, fg_color="transparent")
        options_row.pack(fill="x", pady=(10, 0))
        self.branding_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            options_row, text="Include HexFox branding in PDF export", variable=self.branding_var,
            font=ctk.CTkFont(family=self.mono, size=11), fg_color=theme.ORANGE, hover_color=theme.ORANGE_DARK,
            text_color=theme.TEXT_SECONDARY, checkmark_color=theme.INK,
        ).pack(side="left")

        self.progress = ctk.CTkProgressBar(parent, mode="indeterminate", progress_color=theme.ORANGE,
                                            fg_color=theme.BG_CARD)
        self.progress.pack(fill="x", pady=(14, 0))
        self.progress.set(0)

    def _build_log_section(self, parent):
        self._section_title(parent, "03", "LIVE LOG")
        log_wrap = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=10)
        log_wrap.pack(fill="x")
        self.log_box = ctk.CTkTextbox(log_wrap, height=150, fg_color=theme.BG_CARD, text_color=theme.TEXT_SECONDARY,
                                       font=ctk.CTkFont(family=self.mono, size=11), wrap="none",
                                       activate_scrollbars=True)
        self.log_box.pack(fill="both", expand=True, padx=12, pady=12)
        self.log_box.configure(state="disabled")

    def _build_results_section(self, parent):
        self._section_title(parent, "04", "RESULTS")
        self.results_container = ctk.CTkFrame(parent, fg_color="transparent")
        self.results_container.pack(fill="x")

        self.empty_state = ctk.CTkLabel(
            self.results_container, text="Run a comparison to see Time to First Load and\n"
                                          "Time to Load All Elements for each site.",
            font=ctk.CTkFont(family=self.mono, size=12), text_color=theme.TEXT_MUTED, justify="left",
        )
        self.empty_state.pack(anchor="w", pady=10)

        self.chart = ComparisonChart(parent)
        self.chart.set_mono_font(self.mono)
        self.chart.pack(fill="x", pady=(16, 10))

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def _collect_targets(self):
        targets = []
        for row in self._site_rows:
            label, url = row.get_values()
            if not url:
                continue
            targets.append((label, normalize_url(url)))
        return targets

    def _read_settings(self):
        try:
            timeout = float(self.timeout_entry.get().strip() or 15)
        except ValueError:
            timeout = 15.0
        try:
            concurrency = int(self.concurrency_entry.get().strip() or 8)
        except ValueError:
            concurrency = 8
        try:
            trials = int(self.trials_var.get())
        except ValueError:
            trials = 3
        user_agent = USER_AGENTS.get(self.device_var.get(), list(USER_AGENTS.values())[0])
        network_profile = NETWORK_PRESETS.get(self.network_var.get(), NETWORK_PRESETS["No throttling"])
        cpu_multiplier = CPU_PRESETS.get(self.cpu_var.get(), 1.0)
        return timeout, concurrency, trials, user_agent, self.parse_css_var.get(), network_profile, cpu_multiplier

    def _start_run(self):
        if self._running:
            return
        targets = self._collect_targets()
        if not targets:
            self._log("No websites entered. Add at least one URL above.", color=theme.DANGER)
            return

        self._running = True
        self._stop_event = threading.Event()
        self._summaries = {}
        self._run_order = [f"row-{i}" for i in range(len(targets))]

        self._clear_log()
        self._clear_results()
        for i, (label, url) in enumerate(targets):
            key = f"row-{i}"
            card = SiteResultCard(self.results_container, mono_font=self.mono)
            card.pack(fill="x", pady=6)
            card.set_pending(label, url)
            self._result_cards[key] = card

        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.export_csv_btn.configure(state="disabled")
        self.export_pdf_btn.configure(state="disabled")
        self.status_label.configure(text="Running…", text_color=theme.ORANGE)
        self.progress.configure(mode="indeterminate")
        self.progress.start()

        timeout, concurrency, trials, user_agent, parse_css, network_profile, cpu_multiplier = self._read_settings()
        self._last_network_label = network_profile.name
        self._last_network_description = network_profile.description
        self._last_cpu_label = self.cpu_var.get()
        self._last_trials = trials
        self._last_device_label = self.device_var.get()
        self._log(f"Network: {network_profile.name} ({network_profile.description})  ·  "
                  f"CPU: {self._last_cpu_label}")

        def worker():
            for i, (label, url) in enumerate(targets):
                if self._stop_event.is_set():
                    break
                key = f"row-{i}"
                display_label = label or short_host(url)
                tester = LoadTimeTester(timeout=timeout, concurrency=concurrency, user_agent=user_agent,
                                         parse_css_for_subresources=parse_css, stop_event=self._stop_event,
                                         network_profile=network_profile, cpu_multiplier=cpu_multiplier)
                summary = tester.run(display_label, url, trials, progress=lambda evt: self._events.put(evt))
                self._events.put({"type": "site_summary", "key": key, "summary": summary})
            self._events.put({"type": "all_done"})

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _stop_run(self):
        self._stop_event.set()
        self.status_label.configure(text="Stopping…", text_color=theme.TEXT_MUTED)
        self.stop_btn.configure(state="disabled")

    def _finish_run(self):
        self._running = False
        self.run_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0)
        has_results = any(s.ok for s in self._summaries.values())
        export_state = "normal" if has_results else "disabled"
        self.export_csv_btn.configure(state=export_state)
        self.export_pdf_btn.configure(state=export_state)
        self.status_label.configure(
            text="Done." if not self._stop_event.is_set() else "Stopped.",
            text_color=theme.SUCCESS if not self._stop_event.is_set() else theme.TEXT_MUTED,
        )
        self._update_chart()

    # ------------------------------------------------------------------
    # Event queue draining (runs on the Tk main thread)
    # ------------------------------------------------------------------

    def _poll_events(self):
        try:
            while True:
                evt = self._events.get_nowait()
                self._handle_event(evt)
        except queue.Empty:
            pass
        self.after(80, self._poll_events)

    def _handle_event(self, evt: dict):
        etype = evt.get("type")
        label = evt.get("label", "")

        if etype == "trial_start":
            self._log(f"[{label}] trial {evt['trial']}/{evt['trials']} — requesting {evt['url']}")
        elif etype == "doc_loaded":
            self._log(f"[{label}] document loaded in {format_seconds(evt['elapsed'])} "
                      f"(connection {format_seconds(evt['connect_time'])}, "
                      f"raw {format_seconds(evt['raw_elapsed'])}) — HTTP {evt['status_code']}")
        elif etype == "resources_found":
            tag = "nested css assets" if evt.get("nested") else "resources"
            self._log(f"[{label}] found {evt['count']} {tag} to fetch")
        elif etype == "resource_failed":
            self._log(f"[{label}] ✕ failed {evt['resource_url']} ({evt.get('error')})", color=theme.DANGER)
        elif etype == "site_error":
            self._log(f"[{label}] ✕ error: {evt['error']}", color=theme.DANGER)
        elif etype == "trial_done":
            r = evt["result"]
            if r.ok:
                self._log(f"[{label}] trial {evt['trial']}/{evt['trials']} done — "
                          f"first load {format_seconds(r.raw_time_to_first_load)} raw / "
                          f"{format_seconds(r.time_to_first_load)} total, "
                          f"all elements {format_seconds(r.raw_time_to_all_elements)} raw / "
                          f"{format_seconds(r.time_to_all_elements)} total", color=theme.SUCCESS)
            else:
                self._log(f"[{label}] trial {evt['trial']}/{evt['trials']} failed: {r.error}", color=theme.DANGER)
        elif etype == "site_summary":
            self._summaries[evt["key"]] = evt["summary"]
            card = self._result_cards.get(evt["key"])
            if card:
                card.set_summary(evt["summary"])
            self._update_chart()
        elif etype == "all_done":
            self._finish_run()

    # ------------------------------------------------------------------
    # Small view helpers
    # ------------------------------------------------------------------

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _log(self, message: str, color=None):
        self.log_box.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"{ts}  {message}\n"
        start_index = self.log_box.index("end-1c")
        self.log_box.insert("end", line)
        if color:
            tag = f"c{color}"
            if tag not in self._log_tags:
                self.log_box.tag_config(tag, foreground=color)
                self._log_tags.add(tag)
            self.log_box.tag_add(tag, start_index, "end-1c")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_results(self):
        self.empty_state.pack_forget()
        for card in self._result_cards.values():
            card.destroy()
        self._result_cards = {}

    def _update_chart(self):
        rows = []
        for key in self._run_order:
            summary = self._summaries.get(key)
            if summary and summary.ok:
                rows.append({
                    "label": summary.label,
                    "connect_time": summary.median_connect_time or 0,
                    "raw_first_load": summary.median_raw_first_load or 0,
                    "raw_all_elements": summary.median_raw_all_elements or 0,
                })
        self.chart.set_data(rows)

    def _export_csv(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV file", "*.csv")],
            initialfile=f"hexfox-loadtime-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv",
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["# network_throttle", self._last_network_label])
            writer.writerow(["# cpu_throttle", self._last_cpu_label])
            writer.writerow([
                "label", "url", "ok", "trials", "median_ttfb_s", "median_connect_time_s",
                "median_time_to_first_load_total_s", "median_time_to_first_load_raw_s",
                "median_time_to_all_elements_total_s", "median_time_to_all_elements_raw_s",
                "avg_resource_count", "avg_total_bytes", "avg_failed_resources",
            ])
            for key in self._run_order:
                s: SiteTestSummary = self._summaries.get(key)
                if not s:
                    continue
                writer.writerow([
                    s.label, s.url, s.ok, len(s.runs),
                    f"{s.median_ttfb:.4f}" if s.median_ttfb is not None else "",
                    f"{s.median_connect_time:.4f}" if s.median_connect_time is not None else "",
                    f"{s.median_first_load:.4f}" if s.median_first_load is not None else "",
                    f"{s.median_raw_first_load:.4f}" if s.median_raw_first_load is not None else "",
                    f"{s.median_all_elements:.4f}" if s.median_all_elements is not None else "",
                    f"{s.median_raw_all_elements:.4f}" if s.median_raw_all_elements is not None else "",
                    f"{s.avg_resource_count:.1f}" if s.avg_resource_count is not None else "",
                    f"{s.avg_total_bytes:.0f}" if s.avg_total_bytes is not None else "",
                    f"{s.avg_failed_count:.1f}" if s.avg_failed_count is not None else "",
                ])
        self._log(f"Exported results to {path}", color=theme.SUCCESS)

    def _site_export_row(self, summary: SiteTestSummary) -> dict:
        error = None
        if not summary.ok and summary.runs:
            error = summary.runs[-1].error
        return {
            "label": summary.label,
            "url": summary.url,
            "ok": summary.ok,
            "error": error,
            "trials": len(summary.runs),
            "ttfb": summary.median_ttfb or 0.0,
            "connect_time": summary.median_connect_time or 0.0,
            "total_first_load": summary.median_first_load or 0.0,
            "raw_first_load": summary.median_raw_first_load or 0.0,
            "total_all_elements": summary.median_all_elements or 0.0,
            "raw_all_elements": summary.median_raw_all_elements or 0.0,
            "avg_resource_count": summary.avg_resource_count or 0.0,
            "avg_total_bytes": summary.avg_total_bytes or 0.0,
            "avg_failed_count": summary.avg_failed_count or 0.0,
        }

    def _export_pdf(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF document", "*.pdf")],
            initialfile=f"hexfox-loadtime-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf",
        )
        if not path:
            return

        site_rows = [self._site_export_row(self._summaries[key]) for key in self._run_order if key in self._summaries]
        if not site_rows:
            self._log("Nothing to export yet — run a comparison first.", color=theme.DANGER)
            return

        run_meta = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trials": self._last_trials,
            "device_label": self._last_device_label,
            "network_label": self._last_network_label,
            "network_description": self._last_network_description,
            "cpu_label": self._last_cpu_label,
        }

        try:
            pdf_report.build_pdf(path, run_meta, site_rows, include_branding=self.branding_var.get())
            self._log(f"Exported PDF report to {path}", color=theme.SUCCESS)
        except Exception as exc:
            self._log(f"PDF export failed: {exc}", color=theme.DANGER)


def main():
    app = HexFoxApp()
    app.mainloop()


if __name__ == "__main__":
    main()
