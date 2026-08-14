"""Phase 2 board FDTD smoke: skip unless results/board.s2p exists."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from em_extraction.sparams import read_touchstone

REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_S2P = REPO_ROOT / "results" / "board.s2p"

# Same DC-free Gauss band as openems_mesh / board_extract (f0±fc).
EXCITE_FMIN_HZ = 5e8
EXCITE_FMAX_HZ = 2.5e9
# Lossless-ish 2-port: not the Phase 1 analytical gate.
POWER_CONSERVATION_ABS = 0.2


def test_board_sparams_finite_and_lossless_ish() -> None:
    if not BOARD_S2P.exists():
        pytest.skip(f"{BOARD_S2P} not generated yet")

    measured = read_touchstone(BOARD_S2P)
    for name in ("s11", "s21", "s12", "s22"):
        arr = getattr(measured, name)
        assert np.all(np.isfinite(arr)), f"{name} has non-finite values"

    band = (measured.freqs_hz >= EXCITE_FMIN_HZ) & (measured.freqs_hz <= EXCITE_FMAX_HZ)
    if not np.any(band):
        pytest.skip("no frequency points in the FDTD excite band")

    power = np.abs(measured.s11[band]) ** 2 + np.abs(measured.s21[band]) ** 2
    median_power = float(np.median(power))
    assert median_power == pytest.approx(1.0, abs=POWER_CONSERVATION_ABS), (
        f"median |S11|²+|S21|² = {median_power:.3f} in the excite band "
        f"(expected ~1 ± {POWER_CONSERVATION_ABS})"
    )
