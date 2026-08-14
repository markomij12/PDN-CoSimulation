"""Closed-form parallel-plate transmission line: Z0 and 2-port S-parameters."""

from __future__ import annotations

import numpy as np
from scipy import constants

from em_extraction.geometry import ParallelPlateGeometry
from em_extraction.sparams import SParameterResult

# Characteristic impedance of free space. scipy.constants tracks CODATA.
ETA0_OHM = float(np.sqrt(constants.mu_0 / constants.epsilon_0))
C0_M_PER_S = float(constants.c)


def characteristic_impedance(geom: ParallelPlateGeometry) -> float:
    """Wide-plate Z0 ≈ η0 / sqrt(εr) * h / w.

    Assumes w >> h so fringing fields are negligible. The validation plate has
    w/h ≈ 6.25, so this is a first-order formula, not a full conformal-map Z0.
    """
    return ETA0_OHM / np.sqrt(geom.epsilon_r) * geom.height / geom.width


def analytical_sparams(
    geom: ParallelPlateGeometry,
    freqs_hz: np.ndarray,
) -> SParameterResult:
    """Lossless TL 2-port S-parameters vs `geom.z0_ref`.

    Electrical length θ = βL with β = 2π f sqrt(εr) / c.
    Formulas (Pozar): for z = Z0 / Zref,

        denom = 2 cosθ + j (z + 1/z) sinθ
        S11 = S22 = j (z - 1/z) sinθ / denom
        S21 = S12 = 2 / denom
    """
    freqs_hz = np.asarray(freqs_hz, dtype=float)
    if np.any(freqs_hz < 0):
        raise ValueError("frequencies must be non-negative")

    z0 = characteristic_impedance(geom)
    z = z0 / geom.z0_ref
    beta = 2.0 * np.pi * freqs_hz * np.sqrt(geom.epsilon_r) / C0_M_PER_S
    theta = beta * geom.length

    denom = 2.0 * np.cos(theta) + 1j * (z + 1.0 / z) * np.sin(theta)
    s11 = (1j * (z - 1.0 / z) * np.sin(theta)) / denom
    s21 = 2.0 / denom

    return SParameterResult(
        freqs_hz=freqs_hz,
        s11=s11,
        s21=s21,
        s12=s21.copy(),
        s22=s11.copy(),
        z0_ref=geom.z0_ref,
    )
