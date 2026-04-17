"""Drawdown chart — filled area below zero."""

from matplotlib.ticker import PercentFormatter
from .base import setup_axes


def draw(ax, theme, dd_data, plot_data_out):
    ax.clear()
    setup_axes(ax, theme)

    if dd_data:
        dates = sorted(dd_data.keys())
        vals = [dd_data[d] for d in dates]

        ax.fill_between(dates, vals, 0, color=theme["NEG"], alpha=0.15)
        ax.plot(dates, vals, color=theme["NEG"], linewidth=1.5,
                solid_capstyle="round", alpha=0.9)
        plot_data_out.append(("Drawdown", dates, vals))

    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=1))
    ax.axhline(0, color=theme["BORDER"], linewidth=0.5)
    ax.set_title("Drawdown from Peak", color=theme["FG"], fontsize=11,
                  fontweight="semibold", pad=6, loc="left")
