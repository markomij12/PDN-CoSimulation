"""Before/after |Z(f)|, BOM cost table, Pareto, and optional spatial |Z| map.

Writes gitignored files under ``results/``. Does not import CSXCAD, openEMS, or
pcbnew, and does not launch FDTD. ``z_opt.png`` is the fast-plane overlay
(empty sites vs placed winner from ``plane_impedance``), not 2-port SPICE.
``pareto.png`` is BOM cost vs plane peak |Z| for each count-vector after
placement (fast-plane search, not FDTD, not 2-port SPICE). The optional
2-port ngspice check writes ``z_opt_2port.png`` and ``droop_opt.png`` only
when both DroopResults are present; it does not pick the winner.
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
from optimizer.plane import plane_impedance, plane_z_map
from optimizer.search import ParetoPoint


def write_optimize_artifacts(
    *,
    results_dir: Path,
    stuffing: Sequence[Decap],
    cost_after_usd: float,
    cost_budget_usd: float,
    feasible: bool,
    z_target_ohm: float,
    before: DroopResult | None,
    after: DroopResult | None,
    board: BoardGeometry | None,
    stuffing_at_sites: Sequence[Sequence[Decap]] | None,
    pareto_points: Sequence[ParetoPoint] = (),
    peak_z_after_ohm: float | None = None,
) -> dict[str, Path]:
    """Write plane |Z(f)| overlay, cost table, Pareto, optional 2-port check, spatial map."""
    out = Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Path] = {}
    if board is not None and stuffing_at_sites is not None:
        empty_sites = tuple(() for _ in board.decap_sites)
        freq_hz, z_empty = plane_impedance(board, empty_sites)
        _freq_winner, z_winner = plane_impedance(board, stuffing_at_sites, freq_hz)
        artifacts["z_png"] = _plot_z_before_after(
            freq_hz, z_empty, z_winner, z_target_ohm, out / "z_opt.png"
        )
    if before is not None and after is not None:
        artifacts["z_2port_png"] = _plot_z_2port_check(
            before, after, z_target_ohm, out / "z_opt_2port.png"
        )
        artifacts["droop_png"] = _plot_droop_before_after(
            before, after, out / "droop_opt.png"
        )
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
    if pareto_points:
        artifacts["pareto_png"] = _plot_pareto(
            pareto_points,
            winner_stuffing=stuffing,
            cost_after_usd=cost_after_usd,
            peak_z_after_ohm=peak_z_after_ohm,
            z_target_ohm=z_target_ohm,
            path=out / "pareto.png",
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


def _winner_pareto_point(
    points: Sequence[ParetoPoint],
    winner_stuffing: Sequence[Decap],
    cost_after_usd: float,
    peak_z_after_ohm: float | None,
) -> ParetoPoint | None:
    stuffing = tuple(winner_stuffing)
    for point in points:
        if point.stuffing == stuffing:
            return point
    if peak_z_after_ohm is None:
        return None
    for point in points:
        if point.cost_usd == cost_after_usd and point.peak_z_ohm == peak_z_after_ohm:
            return point
    return None


def _plot_pareto(
    points: Sequence[ParetoPoint],
    *,
    winner_stuffing: Sequence[Decap],
    cost_after_usd: float,
    peak_z_after_ohm: float | None,
    z_target_ohm: float,
    path: Path,
) -> Path:
    winner = _winner_pareto_point(
        points, winner_stuffing, cost_after_usd, peak_z_after_ohm
    )
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    feas_x: list[float] = []
    feas_y: list[float] = []
    infeas_x: list[float] = []
    infeas_y: list[float] = []
    for point in points:
        if winner is not None and (
            point.stuffing == winner.stuffing
            and point.cost_usd == winner.cost_usd
            and point.peak_z_ohm == winner.peak_z_ohm
        ):
            continue
        if point.feasible:
            feas_x.append(point.cost_usd)
            feas_y.append(point.peak_z_ohm)
        else:
            infeas_x.append(point.cost_usd)
            infeas_y.append(point.peak_z_ohm)
    if feas_x:
        ax.scatter(
            feas_x,
            feas_y,
            color="#1f4e79",
            s=36,
            zorder=2,
            label="feasible (cost ≤ budget)",
        )
    if infeas_x:
        ax.scatter(
            infeas_x,
            infeas_y,
            color="#888888",
            s=36,
            zorder=2,
            label="infeasible (over budget)",
        )
    if winner is not None:
        ax.scatter(
            [winner.cost_usd],
            [winner.peak_z_ohm],
            marker="*",
            s=220,
            color="#c44",
            zorder=4,
            label="winner",
        )
        ax.annotate(
            "winner",
            (winner.cost_usd, winner.peak_z_ohm),
            textcoords="offset points",
            xytext=(8, 8),
            fontsize=9,
            color="#c44",
        )
    ax.axhline(
        z_target_ohm,
        color="#c44",
        ls="--",
        lw=0.9,
        label=f"Z_target {z_target_ohm * 1e3:.0f} mΩ",
    )
    peaks = [point.peak_z_ohm for point in points if point.peak_z_ohm > 0]
    if peaks and max(peaks) / min(peaks) >= 10:
        ax.set_yscale("log")
    ax.set_xlabel("BOM cost ($)")
    ax.set_ylabel("peak |Z| (Ω)")
    ax.set_title("Fast-plane search: BOM cost vs peak |Z| (not FDTD, not 2-port SPICE)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _plot_z_before_after(
    freq_hz: np.ndarray,
    z_before: np.ndarray,
    z_after: np.ndarray,
    z_target_ohm: float,
    path: Path,
) -> Path:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.loglog(
        freq_hz,
        np.abs(z_before),
        color="#888888",
        lw=1.3,
        label="before (empty sites, fast plane)",
    )
    ax.loglog(
        freq_hz,
        np.abs(z_after),
        color="#1f4e79",
        lw=1.5,
        label="after (placed winner, fast plane)",
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
    ax.set_title("PDN |Z(f)| at the IC pin (fast plane, not ngspice)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _plot_z_2port_check(
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
        label="before (empty, 2-port)",
    )
    ax.loglog(
        after.freq_hz,
        np.abs(after.z_ohm),
        color="#1f4e79",
        lw=1.5,
        label="after (winner stuffed at port 2)",
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
    ax.set_title(
        "2-port check, all MLCCs at the extracted site — cannot see other vias"
    )
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
    ax.set_title(
        "2-port / port-2 check of winning BOM (not FDTD, not the plane placement result)"
    )
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
