"""Before/after |Z(f)|, BOM cost table, and optional spatial |Z| map.

Writes gitignored files under ``results/``. Does not import CSXCAD, openEMS, or
pcbnew, and does not launch FDTD. The 2-port SPICE check is a post-search
re-sim of empty vs winning stuffing, not the inner loop.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from em_extraction.kicad_reader import BoardGeometry
from spice_models import DroopResult
from spice_models.library import Decap

from optimizer.cost import unit_price_usd
from optimizer.plane import plane_z_map


def write_optimize_artifacts(
    *,
    results_dir: Path,
    stuffing: Sequence[Decap],
    cost_after_usd: float,
    cost_budget_usd: float,
    feasible: bool,
    z_target_ohm: float,
    before: DroopResult,
    after: DroopResult,
    board: BoardGeometry | None,
    stuffing_at_sites: Sequence[Sequence[Decap]] | None,
) -> dict[str, Path]:
    """Write |Z(f)| overlay, cost table, droop overlay, and spatial map if placed."""
    out = Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Path] = {}
    artifacts["z_png"] = _plot_z_before_after(
        before, after, z_target_ohm, out / "z_opt.png"
    )
    artifacts["droop_png"] = _plot_droop_before_after(before, after, out / "droop_opt.png")
    artifacts["bom_txt"] = _write_bom_cost(
        stuffing,
        cost_after_usd,
        cost_budget_usd,
        feasible,
        out / "bom_cost.txt",
    )
    if board is not None and stuffing_at_sites is not None:
        artifacts["spatial_png"] = _plot_spatial(
            board, stuffing_at_sites, out / "z_spatial.png"
        )
    return artifacts


def format_bom_cost_table(
    stuffing: Sequence[Decap],
    cost_after_usd: float,
    cost_budget_usd: float,
    feasible: bool,
) -> str:
    """Plain-text cost table: part, qty, unit $, ext $."""
    counts: Counter[str] = Counter()
    sample: dict[str, Decap] = {}
    for cap in stuffing:
        counts[cap.part] += 1
        sample[cap.part] = cap
    lines = [
        f"{'part':<36} {'case':<6} {'qty':>3} {'unit_$':>8} {'ext_$':>8}",
        "-" * 66,
    ]
    if not stuffing:
        lines.append(f"{'(no MLCCs)':<36} {'':<6} {0:3d} {0:8.2f} {0:8.2f}")
    else:
        for part, qty in counts.items():
            cap = sample[part]
            unit = unit_price_usd(cap)
            lines.append(
                f"{part:<36} {cap.case:<6} {qty:3d} {unit:8.2f} {round(unit * qty, 2):8.2f}"
            )
    lines.append("-" * 66)
    lines.append(f"{'total':<36} {'':<6} {'':>3} {'':>8} {cost_after_usd:8.2f}")
    lines.append(f"{'budget':<36} {'':<6} {'':>3} {'':>8} {cost_budget_usd:8.2f}")
    lines.append("feasible" if feasible else "constraint missed")
    return "\n".join(lines) + "\n"


def _write_bom_cost(
    stuffing: Sequence[Decap],
    cost_after_usd: float,
    cost_budget_usd: float,
    feasible: bool,
    path: Path,
) -> Path:
    path.write_text(
        format_bom_cost_table(stuffing, cost_after_usd, cost_budget_usd, feasible)
    )
    return path


def _plot_z_before_after(
    before: DroopResult,
    after: DroopResult,
    z_target_ohm: float,
    path: Path,
) -> Path:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.loglog(
        before.freq_hz,
        np.abs(before.z_ohm),
        color="#888888",
        lw=1.3,
        label="before (empty)",
    )
    ax.loglog(
        after.freq_hz,
        np.abs(after.z_ohm),
        color="#1f4e79",
        lw=1.5,
        label="after (optimized BOM)",
    )
    ax.axhline(
        z_target_ohm,
        color="#c44",
        ls="--",
        lw=0.9,
        label=f"target {z_target_ohm * 1e3:.0f} mΩ",
    )
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("|Z| (Ω)")
    ax.set_title("PDN |Z(f)| at the IC pin (2-port SPICE check, no FDTD)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _plot_droop_before_after(before: DroopResult, after: DroopResult, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.plot(
        before.time_s * 1e9,
        before.v_ic,
        color="#888888",
        lw=1.2,
        label="before (empty)",
    )
    ax.plot(
        after.time_s * 1e9,
        after.v_ic,
        color="#1f4e79",
        lw=1.4,
        label="after (optimized BOM)",
    )
    ax.set_xlabel("time (ns)")
    ax.set_ylabel("IC pin voltage (V)")
    ax.set_title("PDN voltage droop (ngspice check of winning BOM, no FDTD)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _plot_spatial(
    board: BoardGeometry,
    stuffing_at_sites: Sequence[Sequence[Decap]],
    path: Path,
) -> Path:
    x_m, y_m, peak_z = plane_z_map(board, stuffing_at_sites)
    x_mm = x_m * 1e3
    y_mm = y_m * 1e3
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    mesh = ax.pcolormesh(x_mm, y_mm, peak_z, shading="auto", cmap="viridis")
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label("peak |Z| (Ω)")
    ic = board.ic_power_pin
    if ic is not None:
        ax.plot(ic.x_m * 1e3, ic.y_m * 1e3, marker="*", ms=14, color="#c44", label="U1 (IC)")
    for site, caps in zip(board.decap_sites, stuffing_at_sites, strict=True):
        filled = len(caps) > 0
        ax.plot(
            site.x_m * 1e3,
            site.y_m * 1e3,
            marker="o",
            ms=8,
            color="#f4d35e" if filled else "#dddddd",
            markeredgecolor="#333333",
            linestyle="None",
            label="stuffed via" if filled else "empty via",
        )
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title("Fast-plane peak |Z| vs xy (not openEMS)")
    handles, labels = ax.get_legend_handles_labels()
    seen: set[str] = set()
    uniq_handles: list[object] = []
    uniq_labels: list[str] = []
    for handle, label in zip(handles, labels, strict=True):
        if label in seen:
            continue
        seen.add(label)
        uniq_handles.append(handle)
        uniq_labels.append(label)
    if uniq_labels:
        ax.legend(uniq_handles, uniq_labels, loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path
