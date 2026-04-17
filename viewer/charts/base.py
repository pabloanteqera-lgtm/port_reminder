"""Base chart utilities — crosshair hover system and common styling."""

import matplotlib.dates as mdates
from ..themes import SERIES_COLORS, DEFAULT_COLOR


def get_color(name, theme):
    """Get color for a series name from the current theme."""
    key = SERIES_COLORS.get(name, DEFAULT_COLOR)
    return theme.get(key, theme["MUTED"])


def setup_axes(ax, theme):
    """Apply clean, minimal styling to axes."""
    ax.set_facecolor(theme["BG"])
    ax.tick_params(colors=theme["MUTED"], labelsize=8, length=0, pad=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis="y", color=theme["GRID"], linewidth=0.6, linestyle="-")
    ax.grid(axis="x", color=theme["GRID"], linewidth=0.3, linestyle="-")
    ax.margins(x=0.02)


def setup_legend(ax, theme):
    """Add opaque legend with clean styling."""
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        leg = ax.legend(facecolor=theme["BG"], edgecolor=theme["GRID"],
                        labelcolor=theme["FG"], fontsize=8.5,
                        loc="upper left", framealpha=0.95,
                        borderpad=0.8, handlelength=1.5,
                        labelspacing=0.4)
        leg.get_frame().set_linewidth(0.5)
        for text in leg.get_texts():
            text.set_fontweight("medium")


class CrosshairMixin:
    """Mixin for crosshair hover on date-based charts.
    Host class must have: self.ax, self.canvas, self._plot_data, self.theme
    """

    def init_crosshair(self):
        self._vline = None
        self._annot = None
        self._dots = []
        self.canvas.mpl_connect("motion_notify_event", self._on_hover)

    def _on_hover(self, event):
        # Skip hover while dragging
        if (getattr(self, "_pan_start_px", None) is not None or
                getattr(self, "_axis_drag", None) is not None):
            return

        ax = self.ax
        if self._vline:
            self._vline.remove()
            self._vline = None
        if self._annot:
            self._annot.remove()
            self._annot = None
        for d in self._dots:
            d.remove()
        self._dots = []

        valid_axes = {ax}
        if hasattr(self, '_ax2') and self._ax2 is not None:
            valid_axes.add(self._ax2)
        if event.inaxes not in valid_axes or not self._plot_data:
            self.canvas.draw_idle()
            return

        hover_date = mdates.num2date(event.xdata).date()

        all_dates = set()
        for name, dates, vals in self._plot_data:
            all_dates.update(dates)
        if not all_dates:
            return
        closest = min(all_dates, key=lambda d: abs((d - hover_date).days))

        theme = self.theme
        self._vline = ax.axvline(closest, color=theme["MUTED"],
                                  linewidth=0.5, alpha=0.4)

        lines = [closest.strftime("%b %d, %Y")]
        eur_base = getattr(self, '_eur_base_val', None)
        show_eur = (eur_base is not None
                    and hasattr(self, 'eur_scale_var')
                    and self.eur_scale_var.get())
        for name, dates, vals in self._plot_data:
            if not dates:
                continue
            # Find nearest date in this series (may not have exact match)
            nearest = min(dates, key=lambda d: abs((d - closest).days))
            if abs((nearest - closest).days) <= 7:
                idx = dates.index(nearest)
                v = vals[idx]
                color = get_color(name, theme)
                chart_type = getattr(self, 'chart_type', '')
                if chart_type == "Portfolio Value":
                    first_v = vals[0] if vals else v
                    ret = (v - first_v) / first_v if first_v else 0
                    sign = "+" if ret >= 0 else ""
                    lines.append(f"{name}  \u20ac{v:,.0f}  ({sign}{ret:.2%})")
                elif show_eur:
                    # Only show portfolio return in EUR
                    if name == "Portfolio":
                        eur_val = eur_base * (1 + v)
                        eur_gain = eur_val - eur_base
                        sign = "+" if eur_gain >= 0 else ""
                        lines.append(f"\u20ac{eur_val:,.0f}  ({sign}\u20ac{eur_gain:,.0f})")
                else:
                    lines.append(f"{name}  {v:+.2%}")
                dot = ax.plot(nearest, v, "o", color=color, markersize=5,
                              zorder=5, markeredgewidth=0)
                self._dots.append(dot[0])

        text = "\n".join(lines)

        if show_eur:
            # Tooltip follows mouse position
            self._annot = ax.annotate(
                text,
                xy=(event.xdata, event.ydata),
                xytext=(14, 14), textcoords="offset points",
                fontsize=9, fontfamily="monospace", color=theme["FG"],
                bbox=dict(boxstyle="round,pad=0.5", fc=theme["PANEL"],
                          ec=theme["BORDER"], alpha=0.95, linewidth=0.5),
                ha="left", va="bottom", zorder=10,
            )
        else:
            x_range = ax.get_xlim()
            mid_x = (x_range[0] + x_range[1]) / 2
            x_num = mdates.date2num(closest)
            ha = "left" if x_num < mid_x else "right"
            x_off = 12 if ha == "left" else -12

            self._annot = ax.annotate(
                text,
                xy=(closest, event.ydata),
                xytext=(x_off, 10), textcoords="offset points",
                fontsize=8.5, fontfamily="monospace", color=theme["FG"],
                bbox=dict(boxstyle="round,pad=0.6", fc=theme["PANEL"],
                          ec="none", alpha=0.92),
                ha=ha, va="bottom", zorder=10,
            )
        self.canvas.draw_idle()

    def clear_crosshair(self):
        self._vline = None
        self._annot = None
        self._dots = []
