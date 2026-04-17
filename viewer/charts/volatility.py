"""Rolling volatility chart — portfolio vs benchmarks."""

from matplotlib.ticker import PercentFormatter
from .base import get_color, setup_axes, setup_legend


def draw(ax, theme, port_vol, bench_vols, bench_labels, plot_data_out):
    ax.clear()
    setup_axes(ax, theme)

    if port_vol:
        dates = sorted(port_vol.keys())
        vals = [port_vol[d] for d in dates]
        ax.plot(dates, vals, label="Portfolio", color=get_color("Portfolio", theme),
                linewidth=2, solid_capstyle="round")
        plot_data_out.append(("Portfolio", dates, vals))

    for label in bench_labels:
        if label not in bench_vols:
            continue
        data = bench_vols[label]
        dates = sorted(data.keys())
        vals = [data[d] for d in dates]
        ax.plot(dates, vals, label=label, color=get_color(label, theme),
                linewidth=1.3, alpha=0.85, solid_capstyle="round")
        plot_data_out.append((label, dates, vals))

    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=1))
    ax.set_title("30-Day Rolling Volatility", color=theme["FG"], fontsize=11,
                  fontweight="semibold", pad=6, loc="left")
    setup_legend(ax, theme)
