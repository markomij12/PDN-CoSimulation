"""Shared matplotlib look for PDN impedance / droop figures."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

# Colorblind-friendly PI report palette.
BEFORE = "#6B7280"
AFTER = "#1D4ED8"
TARGET = "#DC2626"
VRM = "#B45309"
WINNER = "#BE123C"
FEASIBLE = "#1D4ED8"
INFEASIBLE = "#9CA3AF"
IC = "#BE123C"
VIA_FULL = "#F59E0B"
VIA_EMPTY = "#E5E7EB"
FILL = "#BFDBFE"

DPI = 180


def apply_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 10.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.9,
            "axes.edgecolor": "#374151",
            "axes.labelcolor": "#111827",
            "axes.facecolor": "#FFFFFF",
            "figure.facecolor": "#FFFFFF",
            "xtick.color": "#4B5563",
            "ytick.color": "#4B5563",
            "grid.color": "#E5E7EB",
            "grid.linewidth": 0.7,
            "legend.frameon": True,
            "legend.framealpha": 0.94,
            "legend.edgecolor": "#E5E7EB",
            "legend.fancybox": False,
            "legend.fontsize": 8.5,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.14,
            "savefig.dpi": DPI,
        }
    )


def style_axes(ax, *, which: str = "both") -> None:
    ax.grid(True, which="major", alpha=0.9)
    if which == "both":
        ax.minorticks_on()
        ax.grid(True, which="minor", alpha=0.35)
    ax.set_axisbelow(True)


def vrm_abs_z(freq_hz: np.ndarray, r_out_ohm: float, l_out_h: float) -> np.ndarray:
    omega = 2.0 * np.pi * np.asarray(freq_hz, dtype=float)
    return np.hypot(r_out_ohm, omega * l_out_h)
