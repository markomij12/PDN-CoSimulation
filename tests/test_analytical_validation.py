"""Phase 1 validation gate: closed-form TL vs (optional) openEMS Touchstone output."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from em_extraction import (
    ParallelPlateGeometry,
    analytical_sparams,
    characteristic_impedance,
)
from em_extraction.sparams import read_touchstone

REPO_ROOT = Path(__file__).resolve().parents[1]
PARALLEL_PLATE_S2P = REPO_ROOT / "results" / "parallel_plate.s2p"

# Independent wide-plate check: Z0 = η0/sqrt(εr) * h/w
# η0 ≈ 376.73 Ω, sqrt(4.5) ≈ 2.1213, h/w = 1.6/10 = 0.16 → ≈ 28.415 Ω
HAND_CALC_Z0_OHM = 28.415

# FDTD is unreliable at DC and at the tail of the Gaussian spectrum.
COMPARE_FMIN_HZ = 2e8
COMPARE_FMAX_HZ = 2.5e9
ABS_S_TOL = 0.05  # few percent of full-scale |S|


def test_characteristic_impedance_matches_hand_calculation() -> None:
    geom = ParallelPlateGeometry.validation_plate()
    z0 = characteristic_impedance(geom)
    assert z0 == pytest.approx(HAND_CALC_Z0_OHM, rel=1e-3)


def test_matched_line_has_zero_reflection() -> None:
    geom = ParallelPlateGeometry.validation_plate()
    matched = ParallelPlateGeometry(
        length=geom.length,
        width=geom.width,
        height=geom.height,
        epsilon_r=geom.epsilon_r,
        z0_ref=characteristic_impedance(geom),
    )
    freqs = np.array([1e8, 5e8, 1e9])
    result = analytical_sparams(matched, freqs)
    assert np.max(np.abs(result.s11)) == pytest.approx(0.0, abs=1e-12)
    assert np.abs(result.s21) == pytest.approx(1.0, abs=1e-12)


def test_openems_sparams_match_analytical() -> None:
    if not PARALLEL_PLATE_S2P.exists():
        pytest.skip(f"{PARALLEL_PLATE_S2P} not generated yet")

    measured = read_touchstone(PARALLEL_PLATE_S2P)
    band = (measured.freqs_hz >= COMPARE_FMIN_HZ) & (measured.freqs_hz <= COMPARE_FMAX_HZ)
    if not np.any(band):
        pytest.skip("no frequency points in the FDTD-valid comparison band")

    freqs = measured.freqs_hz[band]
    predicted = analytical_sparams(ParallelPlateGeometry.validation_plate(), freqs)
    for name in ("s11", "s21"):
        meas = np.abs(getattr(measured, name)[band])
        pred = np.abs(getattr(predicted, name))
        err = np.max(np.abs(meas - pred))
        assert err < ABS_S_TOL, f"{name} max |S| error {err:.3f} exceeds {ABS_S_TOL}"
