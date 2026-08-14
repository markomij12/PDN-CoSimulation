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

# FDTD-valid band is the DC-free Gauss (f0±fc = 0.5–2.5 GHz).
COMPARE_FMIN_HZ = 5e8
COMPARE_FMAX_HZ = 2.5e9
ABS_S_TOL = 0.05  # few percent of full-scale |S|
# Analytical S11 has deep nulls; lumped-port FDTD has a residual floor there.
S11_NULL_ANA = 0.05
S11_NULL_FLOOR = 0.12


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
    s11_m = np.abs(measured.s11[band])
    s21_m = np.abs(measured.s21[band])
    s11_p = np.abs(predicted.s11)
    s21_p = np.abs(predicted.s21)

    err21 = np.max(np.abs(s21_m - s21_p))
    assert err21 < ABS_S_TOL, f"s21 max |S| error {err21:.3f} exceeds {ABS_S_TOL}"

    away_from_null = s11_p >= S11_NULL_ANA
    err11 = np.max(np.abs(s11_m[away_from_null] - s11_p[away_from_null]))
    assert err11 < ABS_S_TOL, f"s11 max |S| error {err11:.3f} exceeds {ABS_S_TOL}"

    null_floor = np.max(s11_m[~away_from_null]) if np.any(~away_from_null) else 0.0
    assert null_floor < S11_NULL_FLOOR, (
        f"s11 FDTD floor {null_floor:.3f} at analytical nulls exceeds {S11_NULL_FLOOR}"
    )
