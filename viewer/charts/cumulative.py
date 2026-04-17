"""Cumulative returns chart — portfolio vs benchmarks."""

from matplotlib.ticker import PercentFormatter
from .base import get_color, setup_axes, setup_legend


def draw(ax, theme, port_returns, bench_returns, bench_labels, plot_data_out,
         portfolio_visible=True):
    """Draw cumulative returns. Returns list of Line2D objects."""
    ax.clear()
    setup_axes(ax, theme)

    lines = []

    if portfolio_visible and port_returns:
        dates = sorted(port_returns.keys())
        vals = [port_returns[d] for d in dates]
        line, = ax.plot(dates, vals, label="Portfolio",
                        color=get_color("Portfolio", theme),
                        linewidth=2, solid_capstyle="round")
        ax.fill_between(dates, vals, 0, color=get_color("Portfolio", theme),
                        alpha=0.06)
        plot_data_out.append(("Portfolio", dates, vals))
        lines.append(line)

    for label in bench_labels:
        if label not in bench_returns:
            continue
        data = bench_returns[label]
        dates = sorted(data.keys())
        vals = [data[d] for d in dates]
        line, = ax.plot(dates, vals, label=label,
                        color=get_color(label, theme),
                        linewidth=1.3, alpha=0.85, solid_capstyle="round")
        plot_data_out.append((label, dates, vals))
        lines.append(line)

    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=1))
    ax.axhline(0, color=theme["BORDER"], linewidth=0.5)
    ax.set_title("Cumulative Returns", color=theme["FG"], fontsize=11,
                  fontweight="semibold", pad=6, loc="left")
    setup_legend(ax, theme)

    return lines
