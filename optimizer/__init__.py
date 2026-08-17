"""Discrete MLCC BOM search: cached Touchstone in, peak |Z(f)| down.

This package searches a discrete MLCC BOM to minimize peak |Z(f)| and MUST NOT
call openEMS / CSXCAD / pcbnew. Cached Touchstone in; FDTD is the validator,
not the inner loop. Generate or refresh the Touchstone with
`python run_pipeline.py --board ...` first.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from spice_models.library import Decap

__all__ = [
    "OptimizeResult",
    "optimize_decap_bom",
]


@dataclass(frozen=True)
class OptimizeResult:
    """BOM stuffing plus before/after peak |Z| and cost. Artifacts under results/."""

    stuffing: tuple[Decap, ...]
    peak_z_before_ohm: float
    peak_z_after_ohm: float
    cost_before_usd: float
    cost_after_usd: float
    cost_budget_usd: float
    feasible: bool
    z_target_ohm: float
    artifacts: dict[str, Path]


def optimize_decap_bom(
    s2p_path: Path | str,
    *,
    cost_budget_usd: float = 0.50,
    z_target_ohm: float = 50e-3,  # match spice_models.simulate.Z_TARGET_OHM
    fmin_hz: float = 1e5,
    fmax_hz: float = 1e9,
    board_path: Path | str | None = None,
    results_dir: Path | str = Path("results"),
) -> OptimizeResult:
    """Search a discrete MLCC BOM to minimize peak |Z(f)| under a cost cap.

    Reads a cached `.s2p`. Does not import or launch CSXCAD, openEMS, or pcbnew.
    `board_path` is reserved for later placement; FDTD remains a validator, not
    the inner loop.
    """
    raise NotImplementedError(
        "optimize_decap_bom is not implemented yet (Phase 4)."
    )
