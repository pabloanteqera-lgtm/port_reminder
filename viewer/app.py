"""Main application window."""

import datetime
import threading
import tkinter as tk

import customtkinter as ctk
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.backends.backend_pdf import PdfPages

plt.rcParams.update({
    "lines.antialiased": True,
    "patch.antialiased": True,
    "text.antialiased": True,
    "figure.dpi": 100,
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "Arial"],
})

from .themes import DARK, LIGHT, SERIES_COLORS, DEFAULT_COLOR
from .data.excel_io import (BROKERS, BENCHMARKS, fetch_benchmarks,
                            save_portfolio_values, save_cashflow)
from .data.loader import load_data, load_cashflows
from .data.compute import (compute_portfolio_totals, compute_portfolio_returns,
                           compute_bench_returns, compute_drawdown,
                           compute_period_returns, compute_rolling_volatility,
                           compute_correlation_matrix, compute_twr,
                           detect_missing_cashflows,
                           filter_by_range, rebase_returns, get_range_cutoff)
from .charts import cumulative, value, period, drawdown, volatility, correlation
from .charts.base import CrosshairMixin, get_color
from .dialogs import AddValuesDialog, CashFlowDialog, ManageBrokersDialog

CHART_TYPES = [
    "Cumulative Returns",
    "Portfolio Value",
    "Weekly Returns",
    "Monthly Returns",
    "Drawdown",
    "Volatility",
    "Correlation",
]

CHART_SHORT = {
    "Cumulative Returns": "Returns",
    "Portfolio Value": "Value",
    "Weekly Returns": "Weekly",
    "Monthly Returns": "Monthly",
    "Drawdown": "Drawdown",
    "Volatility": "Volatility",
    "Correlation": "Correl.",
}

TIME_RANGES = ["1M", "3M", "6M", "YTD", "1Y", "2Y", "3Y", "ALL"]


class App(ctk.CTk, CrosshairMixin):
    def __init__(self):
        super().__init__()
        self.title("Portfolio Tracker")
        self.after(10, lambda: self.state("zoomed"))

        self.is_dark = False
        self.theme = LIGHT
        ctk.set_appearance_mode("light")

        self.broker_names = [b["name"] for b in BROKERS]
        self.bench_labels = [b["label"] for b in BENCHMARKS]

        self.broker_raw, self.bench_raw = load_data()
        self.cashflows = load_cashflows()

        self.time_range = "ALL"
        self.chart_type = CHART_TYPES[0]
        self._custom_from = None
        self._custom_to = None

        self._build_ui()

        self._fetch_thread = threading.Thread(target=self._bg_fetch, daemon=True)
        self._fetch_thread.start()

    def _build_ui(self):
        theme = self.theme
        self.configure(fg_color=theme["BG"])

        self.main = ctk.CTkFrame(self, fg_color=theme["BG"], corner_radius=0)
        self.main.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # ── Sidebar ──
        self.sidebar = ctk.CTkFrame(self.main, fg_color=theme["PANEL"],
                                     width=210, corner_radius=0)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 1))
        self.sidebar.pack_propagate(False)

        inner = ctk.CTkFrame(self.sidebar, fg_color=theme["PANEL"],
                              corner_radius=0)
        inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # Theme toggle
        mode_label = "\u263e  Night" if not self.is_dark else "\u2600  Day"
        ctk.CTkButton(inner, text=mode_label, width=80, height=26,
                      font=("Segoe UI", 11), corner_radius=12,
                      fg_color=theme["GRID"], hover_color=theme["BORDER"],
                      text_color=theme["MUTED"],
                      command=self._toggle_theme).pack(anchor="e", pady=(0, 12))

        # Action buttons
        for text, cmd in [("Edit values", self._open_add_dialog),
                          ("Deposit / Withdrawal", self._open_cashflow_dialog),
                          ("Manage Brokers", self._open_manage_brokers)]:
            ctk.CTkButton(inner, text=text, height=28,
                          font=("Segoe UI", 11), corner_radius=6,
                          fg_color=theme["GRID"], hover_color=theme["BORDER"],
                          text_color=theme["FG"], command=cmd
                          ).pack(fill=tk.X, pady=(0, 4))

        # Status
        self.status_label = ctk.CTkLabel(inner, text="Updating...",
                                          font=("Segoe UI", 10),
                                          text_color=theme["MUTED"],
                                          anchor="w", wraplength=175)
        self.status_label.pack(fill=tk.X, pady=(4, 14))

        # ── Portfolio section ──
        self._portfolio_expanded = False
        self.portfolio_header = ctk.CTkLabel(
            inner, text="\u25B8  Portfolio", font=("Segoe UI", 13, "bold"),
            text_color=theme["PORTFOLIO"], cursor="hand2", anchor="w")
        self.portfolio_header.pack(fill=tk.X, pady=(0, 6))
        self.portfolio_header.bind("<Button-1>", self._toggle_portfolio)

        self.portfolio_visible = tk.BooleanVar(value=True)
        ctk.CTkSwitch(inner, text="Show", variable=self.portfolio_visible,
                       font=("Segoe UI", 11), height=20,
                       switch_width=36, switch_height=18,
                       fg_color=theme["BORDER"],
                       progress_color=theme["PORTFOLIO"],
                       button_color=theme["BG"],
                       button_hover_color=theme["GRID"],
                       text_color=theme["MUTED"],
                       command=self._update_plot).pack(fill=tk.X, pady=(0, 6))

        self.broker_frame = ctk.CTkFrame(inner, fg_color=theme["PANEL"],
                                          corner_radius=0)
        self.broker_vars = {}
        for name in self.broker_names:
            var = tk.BooleanVar(value=True)
            self.broker_vars[name] = var
            ctk.CTkSwitch(self.broker_frame, text=name, variable=var,
                           font=("Segoe UI", 11), height=20,
                           switch_width=36, switch_height=18,
                           fg_color=theme["BORDER"],
                           progress_color=theme["PORTFOLIO"],
                           button_color=theme["BG"],
                           button_hover_color=theme["GRID"],
                           text_color=theme["FG"],
                           command=self._update_plot).pack(fill=tk.X, pady=2,
                                                            padx=(16, 0))

        # Separator
        ctk.CTkFrame(inner, fg_color=theme["GRID"], height=1,
                      corner_radius=0).pack(fill=tk.X, pady=10)

        # ── Benchmarks ──
        ctk.CTkLabel(inner, text="Benchmarks", font=("Segoe UI", 13, "bold"),
                      text_color=theme["FG"], anchor="w").pack(
            fill=tk.X, pady=(0, 6))

        self.bench_vars = {}
        for label in self.bench_labels:
            var = tk.BooleanVar(value=True)
            self.bench_vars[label] = var
            color_key = SERIES_COLORS.get(label, DEFAULT_COLOR)
            color = theme.get(color_key, theme["MUTED"])
            ctk.CTkSwitch(inner, text=label, variable=var,
                           font=("Segoe UI", 11), height=20,
                           switch_width=36, switch_height=18,
                           fg_color=theme["BORDER"],
                           progress_color=color,
                           button_color=theme["BG"],
                           button_hover_color=theme["GRID"],
                           text_color=theme["FG"],
                           command=self._update_plot).pack(fill=tk.X, pady=2)

        # Separator
        ctk.CTkFrame(inner, fg_color=theme["GRID"], height=1,
                      corner_radius=0).pack(fill=tk.X, pady=10)

        # EUR scale toggle
        self.eur_scale_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(inner, text="EUR scale", variable=self.eur_scale_var,
                       font=("Segoe UI", 11), height=20,
                       switch_width=36, switch_height=18,
                       fg_color=theme["BORDER"],
                       progress_color=theme["MUTED"],
                       button_color=theme["BG"],
                       button_hover_color=theme["GRID"],
                       text_color=theme["MUTED"],
                       command=self._update_plot).pack(fill=tk.X, pady=(0, 4))

        # Rebase toggle
        self.rebase_var = tk.BooleanVar(value=True)
        ctk.CTkSwitch(inner, text="Rebase to 0%", variable=self.rebase_var,
                       font=("Segoe UI", 11), height=20,
                       switch_width=36, switch_height=18,
                       fg_color=theme["BORDER"],
                       progress_color=theme["MUTED"],
                       button_color=theme["BG"],
                       button_hover_color=theme["GRID"],
                       text_color=theme["MUTED"],
                       command=self._update_plot).pack(fill=tk.X, pady=(0, 10))

        # Export
        ctk.CTkButton(inner, text="Export PDF", height=28,
                      font=("Segoe UI", 11), corner_radius=6,
                      fg_color=theme["GRID"], hover_color=theme["BORDER"],
                      text_color=theme["MUTED"], command=self._export_pdf
                      ).pack(fill=tk.X)

        # ── Right panel ──
        right = ctk.CTkFrame(self.main, fg_color=theme["BG"], corner_radius=0)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Summary panel — single compact row
        self.summary_frame = ctk.CTkFrame(right, fg_color=theme["PANEL"],
                                           corner_radius=6, height=38)
        self.summary_frame.pack(fill=tk.X, padx=8, pady=(3, 1))
        self.summary_frame.pack_propagate(False)

        sum_inner = ctk.CTkFrame(self.summary_frame, fg_color=theme["PANEL"],
                                  corner_radius=0)
        sum_inner.place(relx=0.5, rely=0.5, anchor="center")

        self.summary_labels = {}
        for i, key in enumerate(["Total", "Today", "Best Week", "Worst Week",
                                  "All-Time", "TWR"]):
            col = ctk.CTkFrame(sum_inner, fg_color=theme["PANEL"],
                                corner_radius=0)
            col.pack(side=tk.LEFT, padx=12)
            ctk.CTkLabel(col, text=key.upper(), font=("Segoe UI", 8),
                          text_color=theme["MUTED"]).pack(side=tk.LEFT, padx=(0, 4))
            lbl = ctk.CTkLabel(col, text="\u2014", font=("Segoe UI", 11, "bold"),
                                text_color=theme["FG"])
            lbl.pack(side=tk.LEFT)
            self.summary_labels[key] = lbl

        # Combined toolbar: chart tabs + time range + custom dates
        toolbar = ctk.CTkFrame(right, fg_color=theme["BG"], corner_radius=0)
        toolbar.pack(fill=tk.X, padx=8, pady=(1, 1))

        # Chart type tabs
        self.chart_btns = {}
        for ct in CHART_TYPES:
            is_active = ct == self.chart_type
            btn = ctk.CTkButton(
                toolbar, text=CHART_SHORT[ct], height=22, width=0,
                font=("Segoe UI", 10), corner_radius=5,
                fg_color=theme["FG"] if is_active else theme["PANEL"],
                hover_color=theme["BORDER"],
                text_color=theme["BG"] if is_active else theme["MUTED"],
                command=lambda c=ct: self._set_chart_type(c))
            btn.pack(side=tk.LEFT, padx=1)
            self.chart_btns[ct] = btn

        # Separator
        ctk.CTkLabel(toolbar, text="|", font=("Segoe UI", 10),
                      text_color=theme["BORDER"]).pack(side=tk.LEFT, padx=4)

        # Time range buttons
        self.range_btns = {}
        for r in TIME_RANGES:
            is_active = r == self.time_range
            btn = ctk.CTkButton(
                toolbar, text=r, height=20, width=30,
                font=("Segoe UI", 10), corner_radius=4,
                fg_color=theme["PORTFOLIO"] if is_active else theme["PANEL"],
                hover_color=theme["BORDER"],
                text_color=theme["BG"] if is_active else theme["MUTED"],
                command=lambda rr=r: self._set_time_range(rr))
            btn.pack(side=tk.LEFT, padx=1)
            self.range_btns[r] = btn

        # Separator
        ctk.CTkLabel(toolbar, text="|", font=("Segoe UI", 10),
                      text_color=theme["BORDER"]).pack(side=tk.LEFT, padx=4)

        # Custom date range
        ctk.CTkLabel(toolbar, text="From", font=("Segoe UI", 9),
                      text_color=theme["MUTED"]).pack(side=tk.LEFT, padx=(0, 2))
        self.date_from = ctk.CTkEntry(toolbar, width=80, height=20,
                                        font=("Segoe UI", 9), corner_radius=4,
                                        border_width=1,
                                        border_color=theme["BORDER"],
                                        fg_color=theme["PANEL"],
                                        text_color=theme["FG"],
                                        placeholder_text="YYYY-MM-DD")
        self.date_from.pack(side=tk.LEFT, padx=(0, 4))

        ctk.CTkLabel(toolbar, text="To", font=("Segoe UI", 9),
                      text_color=theme["MUTED"]).pack(side=tk.LEFT, padx=(0, 2))
        self.date_to = ctk.CTkEntry(toolbar, width=80, height=20,
                                      font=("Segoe UI", 9), corner_radius=4,
                                      border_width=1,
                                      border_color=theme["BORDER"],
                                      fg_color=theme["PANEL"],
                                      text_color=theme["FG"],
                                      placeholder_text="YYYY-MM-DD")
        self.date_to.pack(side=tk.LEFT, padx=(0, 4))

        ctk.CTkButton(toolbar, text="Apply", height=20, width=40,
                      font=("Segoe UI", 9), corner_radius=4,
                      fg_color=theme["PORTFOLIO"],
                      hover_color=theme["POS"],
                      text_color=theme["BG"],
                      command=self._apply_custom_range).pack(side=tk.LEFT)

        # Chart
        chart_container = ctk.CTkFrame(right, fg_color=theme["BG"],
                                        corner_radius=0)
        chart_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 2))

        self.fig, self.ax = plt.subplots(facecolor=theme["BG"])
        self.ax.set_facecolor(theme["BG"])
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_container)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Crosshair
        self._plot_data = []
        self._plot_numdata = []
        self.init_crosshair()

        # Custom pan/zoom
        self._pan_start_px = None
        self._pan_xlim = None
        self._axis_drag = None
        self._axis_drag_start = None
        self._axis_drag_lim = None
        self._default_xlim = None
        self._default_ylim = None
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.canvas.mpl_connect("motion_notify_event", self._on_drag)
        self.canvas.mpl_connect("scroll_event", self._on_scroll)

        self._update_plot()

    def _toggle_theme(self):
        self.is_dark = not self.is_dark
        self.theme = DARK if self.is_dark else LIGHT
        ctk.set_appearance_mode("dark" if self.is_dark else "light")
        # Close any existing matplotlib figure
        plt.close(self.fig)
        self.main.destroy()
        self._build_ui()

    def _set_time_range(self, r):
        self.time_range = r
        self._custom_from = None
        self._custom_to = None
        # Clear date fields
        if hasattr(self, 'date_from'):
            self.date_from.delete(0, tk.END)
            self.date_to.delete(0, tk.END)
        theme = self.theme
        for key, btn in self.range_btns.items():
            is_active = key == r
            btn.configure(
                fg_color=theme["PORTFOLIO"] if is_active else theme["PANEL"],
                text_color=theme["BG"] if is_active else theme["MUTED"])
        self._update_plot()

    def _apply_custom_range(self):
        """Apply custom date range from the From/To fields."""
        from_str = self.date_from.get().strip()
        to_str = self.date_to.get().strip()

        try:
            self._custom_from = (datetime.date.fromisoformat(from_str)
                                 if from_str else None)
        except ValueError:
            self._custom_from = None

        try:
            self._custom_to = (datetime.date.fromisoformat(to_str)
                               if to_str else None)
        except ValueError:
            self._custom_to = None

        # Deselect preset buttons
        self.time_range = "ALL"
        theme = self.theme
        for key, btn in self.range_btns.items():
            btn.configure(fg_color=theme["PANEL"], text_color=theme["MUTED"])

        self._update_plot()

    def _set_chart_type(self, ct):
        self.chart_type = ct
        theme = self.theme
        for key, btn in self.chart_btns.items():
            is_active = key == ct
            btn.configure(
                fg_color=theme["FG"] if is_active else theme["PANEL"],
                text_color=theme["BG"] if is_active else theme["MUTED"])
        self._update_plot()

    def _in_chart(self, event):
        """Check if event is in the main chart area (ax or ax2)."""
        if event.inaxes == self.ax:
            return True
        if hasattr(self, '_ax2') and self._ax2 is not None and event.inaxes == self._ax2:
            return True
        return False

    def _hit_axis(self, event):
        if self._in_chart(event):
            return None
        ax_bbox = self.ax.get_window_extent()
        x, y = event.x, event.y
        if y < ax_bbox.y0 and ax_bbox.x0 <= x <= ax_bbox.x1:
            return "x"
        if x < ax_bbox.x0 and ax_bbox.y0 <= y <= ax_bbox.y1:
            return "y"
        return None

    def _on_press(self, event):
        if event.button != 1:
            return
        if event.dblclick:
            hit = self._hit_axis(event)
            if hit == "x" and self._default_xlim:
                self.ax.set_xlim(self._default_xlim)
                self._fit_y()
                self.canvas.draw_idle()
            elif hit == "y" and self._default_ylim:
                self.ax.set_ylim(self._default_ylim)
                self.canvas.draw_idle()
            elif self._in_chart(event) and self._default_xlim:
                self.ax.set_xlim(self._default_xlim)
                self._fit_y()
                self.canvas.draw_idle()
            return

        hit = self._hit_axis(event)
        if hit:
            self._axis_drag = hit
            self._axis_drag_start = event.x if hit == "x" else event.y
            self._axis_drag_lim = (self.ax.get_xlim() if hit == "x"
                                   else self.ax.get_ylim())
            return

        if self._in_chart(event):
            self._pan_start_px = event.x
            self._pan_xlim = self.ax.get_xlim()

    def _on_release(self, event):
        self._pan_start_px = None
        self._pan_xlim = None
        self._axis_drag = None
        self._axis_drag_start = None
        self._axis_drag_lim = None

    def _on_drag(self, event):
        if self._axis_drag and self._axis_drag_start is not None:
            lim0, lim1 = self._axis_drag_lim
            center = (lim0 + lim1) / 2
            half = (lim1 - lim0) / 2
            if self._axis_drag == "x":
                dx = event.x - self._axis_drag_start
                factor = max(0.1, min(1 - dx * 0.005, 10))
                self.ax.set_xlim(center - half * factor, center + half * factor)
            else:
                dy = event.y - self._axis_drag_start
                factor = max(0.1, min(1 - dy * 0.005, 10))
                self.ax.set_ylim(center - half * factor, center + half * factor)
            self._apply_rebase()
            self._fit_y()
            self.canvas.draw_idle()
            return

        if self._pan_start_px is None:
            return
        x0, x1 = self._pan_xlim
        ax_bbox = self.ax.get_window_extent()
        data_per_px = (x1 - x0) / ax_bbox.width
        dx = (self._pan_start_px - event.x) * data_per_px
        self.ax.set_xlim(x0 + dx, x1 + dx)
        self._apply_rebase()
        self._fit_y()
        self.canvas.draw_idle()

    def _on_scroll(self, event):
        if not self._in_chart(event):
            return
        factor = 0.8 if event.button == "up" else 1.25
        xmin, xmax = self.ax.get_xlim()
        # Keep right edge fixed, expand/contract from the left
        new_width = (xmax - xmin) * factor
        self.ax.set_xlim(xmax - new_width, xmax)
        self._apply_rebase()
        self._fit_y()
        self.canvas.draw_idle()

    def _apply_rebase(self):
        """If rebase is on and chart is cumulative returns,
        shift all line y-data so the leftmost visible point = 0%."""
        if not getattr(self, '_do_rebase', False):
            return
        if self.chart_type != "Cumulative Returns":
            return
        if not self._plot_numdata or not self._line_objects:
            return

        import matplotlib.dates as mdates
        import numpy as np

        xmin = self.ax.get_xlim()[0]

        # Rebuild rebased numdata for _fit_y
        new_numdata = []
        for idx, (name, dates_num, raw_vals) in enumerate(self._plot_numdata):
            # Find first visible index
            i0 = int(dates_num.searchsorted(xmin))
            if i0 >= len(raw_vals):
                i0 = len(raw_vals) - 1
            base = raw_vals[i0]
            # Rebase: (1+r)/(1+base) - 1
            rebased = (1 + raw_vals) / (1 + base) - 1
            self._line_objects[idx].set_ydata(rebased)
            new_numdata.append((name, dates_num, rebased))

            # Update _plot_data for hover tooltip
            dates = [mdates.num2date(d).date() for d in dates_num]
            self._plot_data[idx] = (name, dates, rebased.tolist())

        # Update fill_between for portfolio (first collection after the zero line)
        for coll in self.ax.collections:
            coll.remove()
        if self._plot_data:
            # Portfolio is first entry
            name0, dates0, vals0 = self._plot_data[0]
            if name0 == "Portfolio":
                from .charts.base import get_color
                import datetime as dt
                real_dates = [mdates.num2date(d) for d in self._plot_numdata[0][1]]
                self.ax.fill_between(real_dates, vals0, 0,
                                    color=get_color("Portfolio", self.theme),
                                    alpha=0.06)

        self._rebased_numdata = new_numdata

    def _fit_y(self):
        # Use rebased data if available, otherwise raw
        numdata = getattr(self, '_rebased_numdata', None) or self._plot_numdata
        if not numdata:
            return
        xmin, xmax = self.ax.get_xlim()
        ymin, ymax = float("inf"), float("-inf")
        for name, dates_num, vals_arr in numdata:
            i0 = dates_num.searchsorted(xmin)
            i1 = dates_num.searchsorted(xmax, side="right")
            if i0 >= i1:
                continue
            chunk = vals_arr[i0:i1]
            lo, hi = chunk.min(), chunk.max()
            if lo < ymin:
                ymin = lo
            if hi > ymax:
                ymax = hi
        if ymin < ymax:
            margin = (ymax - ymin) * 0.08 or 0.01
            self.ax.set_ylim(ymin - margin, ymax + margin)

    def _toggle_portfolio(self, event=None):
        self._portfolio_expanded = not self._portfolio_expanded
        if self._portfolio_expanded:
            self.portfolio_header.configure(text="\u25BE  Portfolio")
            self.broker_frame.pack(fill=tk.X, pady=(0, 4),
                                   after=self.portfolio_header)
        else:
            self.portfolio_header.configure(text="\u25B8  Portfolio")
            self.broker_frame.pack_forget()

    def _bg_fetch(self):
        messages = []
        try:
            from telegram_fetch import fetch_and_save
            saved = fetch_and_save()
            if saved:
                for date, values, total in saved:
                    messages.append(f"Telegram: {total:,.0f} EUR ({date})")
            else:
                messages.append("No new Telegram data")
        except Exception as e:
            messages.append(f"Telegram: {e}")
        try:
            messages.append(fetch_benchmarks())
        except Exception as e:
            messages.append(f"Benchmarks: {e}")
        status = "  \u00b7  ".join(messages)
        self.after(0, self._on_fetch_done, status)

    def _on_fetch_done(self, status):
        self.status_label.configure(text=status)
        self.broker_raw, self.bench_raw = load_data()
        self.cashflows = load_cashflows()
        self._update_plot()

    def _open_add_dialog(self):
        dlg = AddValuesDialog(self, self.theme, auto_prompt=False)
        self.wait_window(dlg)
        if dlg.results:
            for date, values in dlg.results:
                save_portfolio_values(date, values)
            self.broker_raw, self.bench_raw = load_data()
            self._update_plot()
            n = len(dlg.results)
            self.status_label.configure(
                text=f"Saved {n} day{'s' if n > 1 else ''} of portfolio data")

    def _open_cashflow_dialog(self):
        dlg = CashFlowDialog(self, self.theme)
        self.wait_window(dlg)
        if dlg.result:
            date, broker, amount, flow_type = dlg.result
            save_cashflow(date, broker, amount, flow_type)
            self.cashflows = load_cashflows()
            self._update_plot()
            self.status_label.configure(
                text=f"{flow_type.title()} \u20ac{amount:,.2f} \u2192 {broker}")

    def _open_manage_brokers(self):
        dlg = ManageBrokersDialog(self, self.theme)
        self.wait_window(dlg)
        if dlg.changed:
            # Reload config and rebuild UI
            from .data.excel_io import _reload_config, BROKERS, BENCHMARKS
            _reload_config()
            from .data import excel_io
            self.broker_names = [b["name"] for b in excel_io.BROKERS]
            self.broker_raw, self.bench_raw = load_data()
            self.cashflows = load_cashflows()
            # Rebuild entire UI to reflect new broker list
            self.main.destroy()
            self._build_ui()
            self._update_plot()
            self.status_label.configure(text="Brokers updated — data reloaded.")

    def _export_pdf(self):
        from tkinter import filedialog
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"portfolio_{datetime.date.today()}.pdf")
        if not filepath:
            return
        with PdfPages(filepath) as pdf:
            pdf.savefig(self.fig)
            fig2, ax2 = plt.subplots(facecolor=self.theme["BG"])
            ax2.set_facecolor(self.theme["BG"])
            ax2.axis("off")
            lines = ["Portfolio Summary", "=" * 40, ""]
            for key, lbl in self.summary_labels.items():
                lines.append(f"{key}: {lbl.cget('text')}")
            ax2.text(0.1, 0.9, "\n".join(lines), transform=ax2.transAxes,
                     fontsize=12, fontfamily="monospace",
                     color=self.theme["FG"], verticalalignment="top")
            pdf.savefig(fig2)
            plt.close(fig2)
        self.status_label.configure(text=f"Exported to {filepath}")

    def _update_summary(self, totals, port_returns):
        theme = self.theme
        if totals:
            dates = sorted(totals.keys())
            latest = totals[dates[-1]]
            self.summary_labels["Total"].configure(text=f"\u20ac{latest:,.0f}")
            if len(dates) >= 2:
                prev = totals[dates[-2]]
                if prev and prev != 0:
                    change = (latest - prev) / prev
                    color = theme["POS"] if change >= 0 else theme["NEG"]
                    self.summary_labels["Today"].configure(
                        text=f"{change:+.2%}", text_color=color)
        else:
            self.summary_labels["Total"].configure(text="\u2014")
            self.summary_labels["Today"].configure(
                text="\u2014", text_color=theme["FG"])

        if totals and len(sorted(totals.keys())) >= 2:
            dates_s = sorted(totals.keys())
            daily_changes = []
            for i in range(1, len(dates_s)):
                prev = totals[dates_s[i - 1]]
                if prev and prev != 0:
                    daily_changes.append((totals[dates_s[i]] - prev) / prev)
            if daily_changes:
                best = max(daily_changes)
                worst = min(daily_changes)
                self.summary_labels["Best Week"].configure(
                    text=f"{best:+.2%}", text_color=theme["POS"])
                self.summary_labels["Worst Week"].configure(
                    text=f"{worst:+.2%}", text_color=theme["NEG"])
        if port_returns:
            last = list(port_returns.values())[-1]
            color = theme["POS"] if last >= 0 else theme["NEG"]
            self.summary_labels["All-Time"].configure(
                text=f"{last:+.2%}", text_color=color)
        else:
            for k in ["Best Week", "Worst Week", "All-Time"]:
                self.summary_labels[k].configure(
                    text="\u2014", text_color=theme["FG"])

        active = [n for n in self.broker_names if self.broker_vars[n].get()]
        all_cf = []
        for name in active:
            all_cf.extend(self.cashflows.get(name, []))
        all_cf.sort()

        if totals and all_cf:
            twr = compute_twr(totals, all_cf)
            if twr:
                last_twr = list(twr.values())[-1]
                color = theme["POS"] if last_twr >= 0 else theme["NEG"]
                self.summary_labels["TWR"].configure(
                    text=f"{last_twr:+.2%}", text_color=color)
            else:
                self.summary_labels["TWR"].configure(
                    text="\u2014", text_color=theme["FG"])
        else:
            self.summary_labels["TWR"].configure(
                text="\u2014", text_color=theme["FG"])

        # Warn about possible missing cashflows
        suspicious = detect_missing_cashflows(totals, all_cf)
        if suspicious:
            dates_str = ", ".join(d.strftime("%Y-%m-%d") for d, _, _ in suspicious[:3])
            extra = f" (+{len(suspicious)-3} more)" if len(suspicious) > 3 else ""
            self.status_label.configure(
                text=f"\u26a0 Possible missing deposit/withdrawal on: {dates_str}{extra}",
                text_color=theme["NEG"])

    def _update_plot(self):
        theme = self.theme
        ax = self.ax
        self._plot_data = []
        self._rebased_numdata = None

        active_brokers = [n for n in self.broker_names
                          if self.broker_vars[n].get()]
        active_bench = [l for l in self.bench_labels
                        if self.bench_vars[l].get()]

        totals = compute_portfolio_totals(self.broker_raw, active_brokers)
        port_returns = compute_portfolio_returns(self.broker_raw, active_brokers)

        port_dates = sorted(port_returns.keys()) if port_returns else []
        start_date = port_dates[0] if port_dates else None

        self._update_summary(totals, port_returns)

        # Determine cutoff from preset or custom range
        custom_from = getattr(self, '_custom_from', None)
        custom_to = getattr(self, '_custom_to', None)

        if custom_from:
            cutoff = custom_from
        else:
            cutoff = get_range_cutoff(self.time_range)

        self._do_rebase = self.rebase_var.get()
        self._custom_to_date = custom_to

        totals_f = filter_by_range(totals, self.time_range)
        bench_returns = compute_bench_returns(self.bench_raw, start_date)

        # Always pass raw returns to chart — _apply_rebase handles shifting
        port_returns_f = port_returns
        bench_returns_f = bench_returns

        ct = self.chart_type

        # Clear colorbar
        cb = getattr(self.fig, "_corr_cbar", None)
        if cb is not None:
            try:
                cb.remove()
            except Exception:
                pass
            self.fig._corr_cbar = None

        self._line_objects = []

        if ct == "Cumulative Returns":
            filtered_bench = {l: bench_returns_f[l] for l in active_bench
                              if l in bench_returns_f}
            self._line_objects = cumulative.draw(
                ax, theme, port_returns_f, filtered_bench,
                active_bench, self._plot_data,
                self.portfolio_visible.get())
        elif ct == "Portfolio Value":
            value.draw(ax, theme, totals_f, self._plot_data)
        elif ct in ("Daily Returns", "Weekly Returns", "Monthly Returns"):
            p = {"Daily Returns": "daily", "Weekly Returns": "weekly",
                 "Monthly Returns": "monthly"}[ct]
            pr = compute_period_returns(totals, p)
            if self.time_range != "ALL":
                cutoff = filter_by_range({d: v for d, v in pr}, self.time_range)
                pr = [(d, v) for d, v in pr if d in cutoff]
            period.draw(ax, theme, pr, ct, self._plot_data)
        elif ct == "Drawdown":
            drawdown.draw(ax, theme, compute_drawdown(totals_f), self._plot_data)
        elif ct == "Volatility":
            port_vol = filter_by_range(
                compute_rolling_volatility(totals), self.time_range)
            bench_vols = {}
            for label in active_bench:
                if label in self.bench_raw:
                    bench_vols[label] = filter_by_range(
                        compute_rolling_volatility(self.bench_raw[label]),
                        self.time_range)
            volatility.draw(ax, theme, port_vol, bench_vols,
                           active_bench, self._plot_data)
        elif ct == "Correlation":
            labels, corr = compute_correlation_matrix(
                {n: self.broker_raw[n] for n in active_brokers
                 if n in self.broker_raw},
                {l: self.bench_raw[l] for l in active_bench
                 if l in self.bench_raw},
                active_brokers)
            correlation.draw(ax, theme, labels, corr)

        self.clear_crosshair()

        # Secondary EUR scale on right y-axis
        # Remove previous secondary axis if it exists
        if hasattr(self, '_ax2') and self._ax2 is not None:
            self._ax2.remove()
            self._ax2 = None

        show_eur = (self.eur_scale_var.get() and totals_f
                    and ct in ("Cumulative Returns", "Drawdown", "Volatility"))
        self._eur_base_val = None
        if show_eur:
            base_val = list(totals_f.values())[0] if totals_f else 1
            self._eur_base_val = base_val
            self._ax2 = ax.twinx()
            self._ax2.set_facecolor("none")
            # Map percentage y-limits to EUR
            ymin, ymax = ax.get_ylim()
            eur_min = base_val * (1 + ymin)
            eur_max = base_val * (1 + ymax)
            self._ax2.set_ylim(eur_min, eur_max)
            self._ax2.yaxis.set_major_formatter(
                lambda x, p: f"\u20ac{x:,.0f}")
            self._ax2.tick_params(colors=theme["MUTED"], labelsize=8, length=0)
            self._ax2.spines["right"].set_visible(False)
            self._ax2.spines["left"].set_visible(False)
            self._ax2.spines["top"].set_visible(False)
            self._ax2.spines["bottom"].set_visible(False)

            # Keep EUR axis in sync when panning
            def sync_eur(event_ax):
                if not hasattr(self, '_ax2') or self._ax2 is None:
                    return
                ymin, ymax = ax.get_ylim()
                self._ax2.set_ylim(base_val * (1 + ymin), base_val * (1 + ymax))
            ax.callbacks.connect("ylim_changed", sync_eur)
        else:
            self._ax2 = None

        import matplotlib.dates as mdates
        import numpy as np
        self._plot_numdata = []
        for name, dates, vals in self._plot_data:
            self._plot_numdata.append((
                name,
                np.array([mdates.date2num(d) for d in dates]),
                np.array(vals),
            ))

        self.fig.set_facecolor(theme["BG"])
        for label in ax.get_xticklabels():
            label.set_rotation(30)
            label.set_ha("right")
        r_margin = 0.90 if show_eur else 0.97
        self.fig.subplots_adjust(left=0.05, right=r_margin, top=0.97, bottom=0.09)

        # Set view to date range
        if self._plot_data:
            xmin_cur, xmax_cur = ax.get_xlim()
            if cutoff is not None:
                xmin_cur = mdates.date2num(cutoff)
            if custom_to is not None:
                xmax_cur = mdates.date2num(custom_to)
            ax.set_xlim(xmin_cur, xmax_cur)

        # Apply rebase (shifts line y-data so leftmost visible = 0%)
        self._apply_rebase()
        self._fit_y()

        self.canvas.draw()

        self._default_xlim = self.ax.get_xlim()
        self._default_ylim = self.ax.get_ylim()
