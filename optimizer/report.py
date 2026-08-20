"""Before/after |Z(f)|, BOM cost table, Pareto, and optional spatial |Z| map.

Writes gitignored files under ``results/``. ``z_opt.png`` is the fast-plane
overlay (empty sites vs placed winner from ``plane_impedance``), not 2-port
SPICE. ``pareto.png`` is BOM cost vs plane peak |Z| in the search band.
The optional 2-port ngspice check writes ``z_opt_2port.png`` and
``droop_opt.png`` only when both DroopResults are present; it does not pick
the winner.
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
from spice_models.library import DEFAULT_VRM, Decap
from spice_models.plot_style import (
    AFTER,
    BEFORE,
    DPI,
    FEASIBLE,
    FILL,
    IC,
    INFEASIBLE,
    TARGET,
    VIA_EMPTY,
    VIA_FULL,
    VRM,
    WINNER,
    apply_style,
    style_axes,
    vrm_abs_z,
)

from optimizer.cost import unit_price_usd
from optimizer.objective import FMAX_HZ, FMIN_HZ
from optimizer.plane import plane_impedance, plane_z_map
from optimizer.search import ParetoPoint

apply_style()


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
    fmin_hz: float = FMIN_HZ,
    fmax_hz: float = FMAX_HZ,
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
            freq_hz,
            z_empty,
            z_winner,
            z_target_ohm,
            out / "z_opt.png",
            fmin_hz=fmin_hz,
            fmax_hz=fmax_hz,
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
        search_freq = np.logspace(np.log10(fmin_hz), np.log10(fmax_hz), 81)
        artifacts["spatial_png"] = _plot_spatial(
            board,
            stuffing_at_sites,
            out / "z_spatial.png",
            freq_hz=search_freq,
            fmin_hz=fmin_hz,
            fmax_hz=fmax_hz,
        )
    if pareto_points:
        artifacts["pareto_png"] = _plot_pareto(
            pareto_points,
            winner_stuffing=stuffing,
            cost_after_usd=cost_after_usd,
            peak_z_after_ohm=peak_z_after_ohm,
            z_target_ohm=z_target_ohm,
            path=out / "pareto.png",
            fmin_hz=fmin_hz,
            fmax_hz=fmax_hz,
            cost_budget_usd=cost_budget_usd,
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


def _band_label(fmin_hz: float, fmax_hz: float) -> str:
    def _hz(value: float) -> str:
        if value >= 1e9:
            return f"{value / 1e9:g} GHz"
        if value >= 1e6:
            return f"{value / 1e6:g} MHz"
        if value >= 1e3:
            return f"{value / 1e3:g} kHz"
        return f"{value:g} Hz"

    return f"{_hz(fmin_hz)}–{_hz(fmax_hz)}"


def _draw_z_overlay(
    ax,
    freq_hz: np.ndarray,
    z_before: np.ndarray,
    z_after: np.ndarray,
    z_target_ohm: float,
    *,
    before_label: str,
    after_label: str,
    show_vrm: bool,
    fill_under_target: bool,
) -> None:
    mag_before = np.abs(z_before)
    mag_after = np.abs(z_after)
    ax.loglog(freq_hz, mag_before, color=BEFORE, lw=1.8, label=before_label)
    ax.loglog(freq_hz, mag_after, color=AFTER, lw=2.2, label=after_label)
    if fill_under_target:
        under = mag_after <= z_target_ohm
        if np.any(under):
            ax.fill_between(
                freq_hz,
                mag_after,
                z_target_ohm,
                where=under,
                color=FILL,
                alpha=0.55,
                interpolate=True,
                label="under target",
                zorder=0,
            )
    ax.axhline(
        z_target_ohm,
        color=TARGET,
        ls="--",
        lw=1.15,
        label=f"target {z_target_ohm * 1e3:.0f} mΩ",
    )
    if show_vrm:
        ax.loglog(
            freq_hz,
            vrm_abs_z(freq_hz, DEFAULT_VRM.r_out_ohm, DEFAULT_VRM.l_out_h),
            color=VRM,
            ls=":",
            lw=1.4,
            label=f"VRM |R+jωL| ({DEFAULT_VRM.l_out_h * 1e9:g} nH)",
        )
    style_axes(ax)
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("|Z| (Ω)")


def _plot_pareto(
    points: Sequence[ParetoPoint],
    *,
    winner_stuffing: Sequence[Decap],
    cost_after_usd: float,
    peak_z_after_ohm: float | None,
    z_target_ohm: float,
    path: Path,
    fmin_hz: float = FMIN_HZ,
    fmax_hz: float = FMAX_HZ,
    cost_budget_usd: float = 0.50,
) -> Path:
    winner = _winner_pareto_point(
        points, winner_stuffing, cost_after_usd, peak_z_after_ohm
    )
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
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
            color=FEASIBLE,
            s=52,
            zorder=2,
            edgecolors="white",
            linewidths=0.6,
            label="feasible (≤ budget)",
        )
    if infeas_x:
        ax.scatter(
            infeas_x,
            infeas_y,
            color=INFEASIBLE,
            s=44,
            zorder=2,
            edgecolors="white",
            linewidths=0.5,
            label="over budget",
        )
    if winner is not None:
        ax.scatter(
            [winner.cost_usd],
            [winner.peak_z_ohm],
            marker="*",
            s=280,
            color=WINNER,
            zorder=4,
            edgecolors="white",
            linewidths=0.6,
            label="winner",
        )
        ax.annotate(
            f"winner  ${winner.cost_usd:.2f}\n{winner.peak_z_ohm * 1e3:.1f} mΩ",
            (winner.cost_usd, winner.peak_z_ohm),
            textcoords="offset points",
            xytext=(-8, 14),
            ha="right",
            fontsize=8.5,
            color=WINNER,
            fontweight="bold",
        )
    ax.axhline(
        z_target_ohm,
        color=TARGET,
        ls="--",
        lw=1.15,
        label=f"Z_target {z_target_ohm * 1e3:.0f} mΩ",
    )
    ax.axvline(cost_budget_usd, color="#6B7280", ls=":", lw=1.1, label=f"budget ${cost_budget_usd:.2f}")
    peaks = [point.peak_z_ohm for point in points if point.peak_z_ohm > 0]
    if peaks and max(peaks) / min(peaks) >= 8:
        ax.set_yscale("log")
    ax.set_xlabel("BOM cost ($)")
    ax.set_ylabel(f"peak |Z| ({_band_label(fmin_hz, fmax_hz)})")
    ax.set_title("Search: BOM cost vs peak |Z|")
    style_axes(ax, which="major")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def _plot_z_before_after(
    freq_hz: np.ndarray,
    z_before: np.ndarray,
    z_after: np.ndarray,
    z_target_ohm: float,
    path: Path,
    *,
    fmin_hz: float = FMIN_HZ,
    fmax_hz: float = FMAX_HZ,
) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.7), sharey=False)
    _draw_z_overlay(
        axes[0],
        freq_hz,
        z_before,
        z_after,
        z_target_ohm,
        before_label="empty plane",
        after_label="winner",
        show_vrm=True,
        fill_under_target=False,
    )
    axes[0].set_title("|Z(f)| at U1")
    axes[0].set_xlim(freq_hz[0], freq_hz[-1])
    band = (freq_hz >= fmin_hz) & (freq_hz <= fmax_hz)
    if np.count_nonzero(band) >= 2:
        _draw_z_overlay(
            axes[1],
            freq_hz[band],
            z_before[band],
            z_after[band],
            z_target_ohm,
            before_label="empty plane",
            after_label="winner",
            show_vrm=False,
            fill_under_target=True,
        )
        axes[1].set_xlim(fmin_hz, fmax_hz)
    else:
        _draw_z_overlay(
            axes[1],
            freq_hz,
            z_before,
            z_after,
            z_target_ohm,
            before_label="empty plane",
            after_label="winner",
            show_vrm=False,
            fill_under_target=True,
        )
    axes[1].set_title(f"Search band ({_band_label(fmin_hz, fmax_hz)})")
    handles, labels = axes[0].get_legend_handles_labels()
    extra_h, extra_l = axes[1].get_legend_handles_labels()
    for handle, label in zip(extra_h, extra_l, strict=True):
        if label not in labels:
            handles.append(handle)
            labels.append(label)
    fig.legend(handles, labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def _plot_z_2port_check(
    before: DroopResult,
    after: DroopResult,
    z_target_ohm: float,
    path: Path,
) -> Path:
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    _draw_z_overlay(
        ax,
        before.freq_hz,
        before.z_ohm,
        after.z_ohm,
        z_target_ohm,
        before_label="empty (2-port)",
        after_label="winner at port 2",
        show_vrm=True,
        fill_under_target=False,
    )
    ax.set_title("2-port check — every MLCC parked at the extracted via")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def _plot_droop_before_after(before: DroopResult, after: DroopResult, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.plot(before.time_s * 1e9, before.v_ic, color=BEFORE, lw=1.7, label="empty")
    ax.plot(after.time_s * 1e9, after.v_ic, color=AFTER, lw=2.1, label="winner")
    ax.axhline(
        before.v_pre_step,
        color="#9CA3AF",
        ls="--",
        lw=0.9,
        label=f"pre-step {before.v_pre_step:.3f} V",
    )
    ax.set_xlabel("time (ns)")
    ax.set_ylabel("IC pin voltage (V)")
    ax.set_title("2-port check — load-step droop")
    style_axes(ax, which="major")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def _plot_spatial(
    board: BoardGeometry,
    stuffing_at_sites: Sequence[Sequence[Decap]],
    path: Path,
    *,
    freq_hz: np.ndarray | None = None,
    fmin_hz: float = FMIN_HZ,
    fmax_hz: float = FMAX_HZ,
) -> Path:
    x_m, y_m, peak_z = plane_z_map(board, stuffing_at_sites, freq_hz, nx=41, ny=29)
    x_mm = x_m * 1e3
    y_mm = y_m * 1e3
    fig, ax = plt.subplots(figsize=(8.0, 5.1))
    mesh = ax.pcolormesh(
        x_mm,
        y_mm,
        peak_z * 1e3,
        shading="gouraud",
        cmap="cividis",
        rasterized=True,
    )
    cbar = fig.colorbar(mesh, ax=ax, pad=0.02, fraction=0.046)
    cbar.set_label(f"peak |Z| (mΩ, {_band_label(fmin_hz, fmax_hz)})")
    ic = board.ic_power_pin
    if ic is not None:
        ax.plot(
            ic.x_m * 1e3,
            ic.y_m * 1e3,
            marker="*",
            ms=18,
            color=IC,
            markeredgecolor="white",
            markeredgewidth=0.6,
            linestyle="None",
            label="U1 (IC)",
            zorder=5,
        )
    for site, caps in zip(board.decap_sites, stuffing_at_sites, strict=True):
        filled = len(caps) > 0
        ax.plot(
            site.x_m * 1e3,
            site.y_m * 1e3,
            marker="o",
            ms=11 if filled else 8,
            color=VIA_FULL if filled else VIA_EMPTY,
            markeredgecolor="#111827",
            markeredgewidth=0.7,
            linestyle="None",
            label="stuffed via" if filled else "empty via",
            zorder=4,
        )
        if filled:
            ax.annotate(
                str(len(caps)),
                (site.x_m * 1e3, site.y_m * 1e3),
                textcoords="offset points",
                xytext=(7, 6),
                fontsize=8,
                color="#111827",
            )
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title("Peak |Z| across the plane")
    style_axes(ax, which="major")
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
        ax.legend(uniq_handles, uniq_labels, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path
