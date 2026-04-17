"""Portfolio value chart — absolute EUR over time."""

from .base import get_color, setup_axes, setup_legend


def draw(ax, theme, totals, plot_data_out):
    ax.clear()
    setup_axes(ax, theme)

    if totals:
        dates = sorted(totals.keys())
        vals = [totals[d] for d in dates]
        color = get_color("Portfolio", theme)
        ax.plot(dates, vals, label="Portfolio", color=color,
                linewidth=2, solid_capstyle="round")
        ax.fill_between(dates, vals, min(vals) * 0.98, color=color, alpha=0.08)
        plot_data_out.append(("Portfolio", dates, vals))

        ax.yaxis.set_major_formatter(
            lambda x, p: f"\u20ac{x:,.0f}")

    ax.set_title("Portfolio Value", color=theme["FG"], fontsize=11,
                  fontweight="semibold", pad=6, loc="left")
    setup_legend(ax, theme)
