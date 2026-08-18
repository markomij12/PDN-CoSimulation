"""Discrete MLCC BOM search: cavity-plane inner loop, peak |Z(f)| down.

This package searches a discrete MLCC BOM and via placement to minimize
peak |Z(f)| and MUST NOT call openEMS / CSXCAD / pcbnew. The inner loop is
the fast cavity plane, not ngspice. Cached Touchstone is used only for a
post-search 2-port SPICE *check* of the plane winner (does not pick the
BOM). Missing `.s2p` or ngspice skips that check; plane artifacts still
write. Generate or refresh the Touchstone with
`python run_pipeline.py --board ...` first.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from spice_models.library import Decap

__all__ = [
    "OptimizeResult",
    "optimize_decap_bom",
]


@dataclass(frozen=True)
class OptimizeResult:
    """BOM stuffing plus before/after peak |Z| and cost. Artifacts under results/.

    ``peak_z_before_ohm`` / ``peak_z_after_ohm`` are fast-plane peak |Z_ic|,
    not 2-port SPICE. ``peak_z_after_freq_hz`` is the frequency of the
    winner's plane peak |Z|. ``f_cross_hz`` is the lowest in-band f where
    |Z| > Z_target (``None`` = met in-band). ``plane_peak_z_ohm`` is the
    winner's plane peak (same as ``peak_z_after_ohm``). ``spice_peak_z_*``
    are the optional 2-port check (None when `.s2p` or ngspice is missing).
    """

    stuffing: tuple[Decap, ...]
    peak_z_before_ohm: float
    peak_z_after_ohm: float
    peak_z_after_freq_hz: float
    f_cross_hz: float | None
    cost_before_usd: float
    cost_after_usd: float
    cost_budget_usd: float
    feasible: bool
    z_target_ohm: float
    artifacts: dict[str, Path]
    placement_site_indices: tuple[int, ...] = ()
    plane_peak_z_ohm: float | None = None
    spice_peak_z_before_ohm: float | None = None
    spice_peak_z_after_ohm: float | None = None


def optimize_decap_bom(
    s2p_path: Path | str,
    *,
    cost_budget_usd: float = 0.50,
    z_target_ohm: float = 50e-3,  # match spice_models.simulate.Z_TARGET_OHM
    fmin_hz: float = 1e5,
    fmax_hz: float = 1e9,
    board_path: Path | str | None = None,
    results_dir: Path | str = Path("results"),
    max_count: int = 2,
) -> OptimizeResult:
    """Search a discrete MLCC BOM and placement to minimize plane peak |Z(f)|.

    Requires ``board_path`` (e.g. ``boards/pdn_test.kicad_pcb``). The inner
    loop is the fast cavity plane (``search_plane_grid``), not ngspice. Does
    not import or launch CSXCAD, openEMS, or pcbnew. After the search, an
    optional 2-port SPICE check re-sims empty vs winner stuffing at the
    extracted site (needs cached `.s2p` and ngspice). Missing `.s2p` or
    ngspice skips that check; plane plots still write. The check does not
    re-rank the winner. `max_count` is 0–N of each catalog part (default 2
    → 27 stuffing vectors).
    """
    if board_path is None:
        raise ValueError(
            "board_path is required for the plane-scored search "
            "(e.g. boards/pdn_test.kicad_pcb); the optimizer does not "
            "silently skip placement"
        )

    # Lazy import: search.py imports optimizer.cost / objective / plane, not this module.
    from em_extraction.kicad_reader import read_board
    from optimizer.objective import f_cross_hz, peak_abs_z, peak_abs_z_freq
    from optimizer.plane import plane_impedance
    from optimizer.report import write_optimize_artifacts
    from optimizer.search import search_plane_grid
    from spice_models import MissingS2pError, from_sparams, simulate_droop
    from spice_models.ngspice import NgspiceNotInstalledError

    board = read_board(board_path)
    outcome = search_plane_grid(
        board,
        cost_budget_usd=cost_budget_usd,
        fmin_hz=fmin_hz,
        fmax_hz=fmax_hz,
        max_count=max_count,
    )

    before = None
    after = None
    spice_peak_z_before_ohm: float | None = None
    spice_peak_z_after_ohm: float | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="pdn_opt_check_") as scratch:
            scratch_dir = Path(scratch)
            before = simulate_droop(
                from_sparams(s2p_path, decaps=()),
                results_dir=scratch_dir / "before",
            )
            after = simulate_droop(
                from_sparams(s2p_path, decaps=outcome.stuffing),
                results_dir=scratch_dir / "after",
            )
            spice_peak_z_before_ohm = peak_abs_z(
                before.z_ohm, before.freq_hz, fmin_hz, fmax_hz
            )
            spice_peak_z_after_ohm = peak_abs_z(
                after.z_ohm, after.freq_hz, fmin_hz, fmax_hz
            )
    except (MissingS2pError, NgspiceNotInstalledError):
        before = None
        after = None
        spice_peak_z_before_ohm = None
        spice_peak_z_after_ohm = None

    freq_winner, z_winner = plane_impedance(board, outcome.stuffing_at_sites)
    peak_z_after_freq_hz = peak_abs_z_freq(
        z_winner, freq_winner, fmin_hz, fmax_hz
    )
    cross_hz = f_cross_hz(
        z_winner, freq_winner, z_target_ohm, fmin_hz, fmax_hz
    )

    artifacts = write_optimize_artifacts(
        results_dir=Path(results_dir),
        stuffing=outcome.stuffing,
        cost_after_usd=outcome.cost_after_usd,
        cost_budget_usd=cost_budget_usd,
        feasible=outcome.feasible,
        z_target_ohm=z_target_ohm,
        before=before,
        after=after,
        board=board,
        stuffing_at_sites=outcome.stuffing_at_sites,
        pareto_points=outcome.evaluated_points,
        peak_z_after_ohm=outcome.peak_z_after_ohm,
    )

    return OptimizeResult(
        stuffing=outcome.stuffing,
        peak_z_before_ohm=outcome.peak_z_before_ohm,
        peak_z_after_ohm=outcome.peak_z_after_ohm,
        peak_z_after_freq_hz=peak_z_after_freq_hz,
        f_cross_hz=cross_hz,
        cost_before_usd=outcome.cost_before_usd,
        cost_after_usd=outcome.cost_after_usd,
        cost_budget_usd=cost_budget_usd,
        feasible=outcome.feasible,
        z_target_ohm=z_target_ohm,
        artifacts=artifacts,
        placement_site_indices=outcome.placement_site_indices,
        plane_peak_z_ohm=outcome.peak_z_after_ohm,
        spice_peak_z_before_ohm=spice_peak_z_before_ohm,
        spice_peak_z_after_ohm=spice_peak_z_after_ohm,
    )
