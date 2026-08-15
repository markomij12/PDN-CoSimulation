"""Phase 3 ngspice transient: skip if ngspice is missing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from em_extraction import ParallelPlateGeometry, analytical_sparams
from em_extraction.sparams import write_touchstone
from spice_models import from_sparams, ngspice_available
from spice_models.simulate import simulate_droop

REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_S2P = REPO_ROOT / "results" / "board.s2p"

# Smaller than the ~5 mV DC drop (0.5 A × 10 mΩ) plus inductive first droop.
MIN_DROOP_V = 1e-3


def test_load_step_produces_finite_measurable_droop(tmp_path: Path) -> None:
    if not ngspice_available():
        pytest.skip("ngspice not installed")

    s2p = tmp_path / "plate.s2p"
    geom = ParallelPlateGeometry.validation_plate()
    write_touchstone(analytical_sparams(geom, np.linspace(5e8, 8e8, 20)), s2p)
    result = simulate_droop(from_sparams(s2p), results_dir=tmp_path / "out")

    assert np.all(np.isfinite(result.v_ic))
    assert np.all(np.isfinite(result.z_ohm))
    assert result.v_ic.size > 10
    assert float(np.ptp(result.v_ic)) > MIN_DROOP_V
    assert result.peak_droop_v > MIN_DROOP_V
    assert result.droop_png.is_file()
    assert result.z_png.is_file()


def test_board_s2p_transient_when_present(tmp_path: Path) -> None:
    if not ngspice_available():
        pytest.skip("ngspice not installed")
    if not BOARD_S2P.exists():
        pytest.skip(f"{BOARD_S2P} not generated yet")

    result = simulate_droop(from_sparams(BOARD_S2P), results_dir=tmp_path / "out")
    assert np.all(np.isfinite(result.v_ic))
    assert result.peak_droop_v > MIN_DROOP_V
