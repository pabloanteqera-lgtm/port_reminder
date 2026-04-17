"""Period returns bar chart — daily/weekly/monthly."""

from matplotlib.ticker import PercentFormatter
from .base import setup_axes


def draw(ax, theme, period_returns, period_label, plot_data_out):
    ax.clear()
    setup_axes(ax, theme)

    if not period_returns:
        ax.set_title(period_label, color=theme["FG"], fontsize=11,
                      fontweight="semibold", pad=6, loc="left")
        return

    dates = [d for d, _ in period_returns]
    vals = [v for _, v in period_returns]
    colors = [theme["POS"] if v >= 0 else theme["NEG"] for v in vals]

    if "Weekly" in period_label:
        width = 5
    elif "Monthly" in period_label:
        width = 20
    else:
        width = 0.7 if len(dates) < 50 else 0.4
    ax.bar(dates, vals, color=colors, width=width, alpha=0.8,
           edgecolor="none")

    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=1))
    ax.axhline(0, color=theme["BORDER"], linewidth=0.5)
    ax.set_title(period_label, color=theme["FG"], fontsize=11,
                  fontweight="semibold", pad=6, loc="left")

    plot_data_out.append(("Return", dates, vals))
