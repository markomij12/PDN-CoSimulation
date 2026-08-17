"""Discrete MLCC BOM search: cached Touchstone in, peak |Z(f)| down.

This package searches a discrete MLCC BOM to minimize peak |Z(f)| and MUST NOT
call openEMS / CSXCAD / pcbnew. Cached Touchstone in; FDTD is the validator,
not the inner loop. Generate or refresh the Touchstone with
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

    ``peak_z_before_ohm`` / ``peak_z_after_ohm`` are 2-port SPICE. Placement
    and ``plane_peak_z_ohm`` come from the fast plane when ``board_path`` is set.
    """

    stuffing: tuple[Decap, ...]
    peak_z_before_ohm: float
    peak_z_after_ohm: float
    cost_before_usd: float
    cost_after_usd: float
    cost_budget_usd: float
    feasible: bool
    z_target_ohm: float
    artifacts: dict[str, Path]
    placement_site_indices: tuple[int, ...] = ()
    plane_peak_z_ohm: float | None = None


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
    """Search a discrete MLCC BOM to minimize peak |Z(f)| under a cost cap.

    Reads a cached `.s2p`. Does not import or launch CSXCAD, openEMS, or pcbnew.
    Count/value search stays on the 2-port ngspice grid. If `board_path` is
    set, the winning stuffing is assigned across VCC vias with the fast plane
    (not FDTD). If `board_path` is None, placement stays empty. `max_count` is
    0–N of each catalog part (default 2 → 27 candidates).
    """
    # Lazy import: search.py imports optimizer.cost / objective, not this module.
    from optimizer.report import write_optimize_artifacts
    from optimizer.search import search_count_grid
    from spice_models import from_sparams, simulate_droop

    outcome = search_count_grid(
        s2p_path,
        cost_budget_usd=cost_budget_usd,
        fmin_hz=fmin_hz,
        fmax_hz=fmax_hz,
        max_count=max_count,
    )

    placement_site_indices: tuple[int, ...] = ()
    plane_peak_z_ohm: float | None = None
    board = None
    stuffing_at_sites: tuple[tuple[Decap, ...], ...] | None = None
    if board_path is not None:
        import numpy as np

        from em_extraction.kicad_reader import read_board
        from optimizer.plane import assign_caps_to_sites, placement_site_indices as site_indices

        board = read_board(board_path)
        freq_hz = np.logspace(np.log10(fmin_hz), np.log10(fmax_hz), 81)
        stuffing_at_sites, _unused, plane_peak_z_ohm = assign_caps_to_sites(
            board, outcome.stuffing, freq_hz
        )
        placement_site_indices = site_indices(outcome.stuffing, stuffing_at_sites)

    results = Path(results_dir)
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
        artifacts = write_optimize_artifacts(
            results_dir=results,
            stuffing=outcome.stuffing,
            cost_after_usd=outcome.cost_after_usd,
            cost_budget_usd=cost_budget_usd,
            feasible=outcome.feasible,
            z_target_ohm=z_target_ohm,
            before=before,
            after=after,
            board=board,
            stuffing_at_sites=stuffing_at_sites,
        )

    return OptimizeResult(
        stuffing=outcome.stuffing,
        peak_z_before_ohm=outcome.peak_z_before_ohm,
        peak_z_after_ohm=outcome.peak_z_after_ohm,
        cost_before_usd=outcome.cost_before_usd,
        cost_after_usd=outcome.cost_after_usd,
        cost_budget_usd=cost_budget_usd,
        feasible=outcome.feasible,
        z_target_ohm=z_target_ohm,
        artifacts=artifacts,
        placement_site_indices=placement_site_indices,
        plane_peak_z_ohm=plane_peak_z_ohm,
    )
