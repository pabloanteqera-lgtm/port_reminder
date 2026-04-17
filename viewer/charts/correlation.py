"""Correlation matrix heatmap."""

import numpy as np


def draw(ax, theme, labels, corr_matrix):
    ax.clear()
    fig = ax.figure

    # Remove any existing colorbars from previous draws
    for attr in ("_corr_cbar",):
        cb = getattr(fig, attr, None)
        if cb is not None:
            try:
                cb.remove()
            except Exception:
                pass
            setattr(fig, attr, None)

    if len(labels) < 2 or corr_matrix.size == 0:
        ax.set_facecolor(theme["BG"])
        ax.text(0.5, 0.5, "Not enough data",
                ha="center", va="center", color=theme["MUTED"],
                fontsize=11, transform=ax.transAxes)
        ax.set_title("Correlation", color=theme["FG"], fontsize=11,
                      fontweight="semibold", pad=6, loc="left")
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        return

    n = len(labels)
    im = ax.imshow(corr_matrix, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels, fontsize=8, color=theme["MUTED"],
                        rotation=45, ha="right")
    ax.set_yticklabels(labels, fontsize=8, color=theme["MUTED"])
    ax.tick_params(length=0, pad=6)

    for i in range(n):
        for j in range(n):
            val = corr_matrix[i, j]
            text_color = "#FFFFFF" if abs(val) > 0.5 else theme["FG"]
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=9, color=text_color, fontweight="medium")

    ax.set_facecolor(theme["BG"])
    for spine in ax.spines.values():
        spine.set_visible(False)

    cbar = fig.colorbar(im, ax=ax, shrink=0.75, pad=0.02)
    cbar.ax.tick_params(colors=theme["MUTED"], labelsize=7, length=0)
    cbar.outline.set_visible(False)
    fig._corr_cbar = cbar

    ax.set_title("Correlation Matrix", color=theme["FG"], fontsize=11,
                  fontweight="semibold", pad=6, loc="left")
