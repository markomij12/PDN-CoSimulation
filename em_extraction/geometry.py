"""Geometry types for Phase 1 (parallel plate) and the Phase 2 KiCad seam."""

from __future__ import annotations

from dataclasses import dataclass

# Solver-validation plate: Z0 tens of ohms so 50 Ω S-params are well-conditioned.
# This is NOT a realistic PDN plane (those have Z0 ~ 1 Ω and milliohm impedance).
VALIDATION_LENGTH_M = 50e-3
VALIDATION_WIDTH_M = 10e-3
VALIDATION_HEIGHT_M = 1.6e-3
VALIDATION_EPSILON_R = 4.5
DEFAULT_Z0_REF_OHM = 50.0


@dataclass(frozen=True)
class ParallelPlateGeometry:
    """Two PEC plates separated by a homogeneous dielectric; wave travels along `length`.

    Lengths are in meters. `z0_ref` is the S-parameter port reference, not the plate Z0.
    """

    length: float
    width: float
    height: float
    epsilon_r: float
    z0_ref: float = DEFAULT_Z0_REF_OHM

    def __post_init__(self) -> None:
        if min(self.length, self.width, self.height, self.epsilon_r, self.z0_ref) <= 0:
            raise ValueError("length, width, height, epsilon_r, and z0_ref must be positive")

    @classmethod
    def validation_plate(cls) -> ParallelPlateGeometry:
        """Thick, relatively narrow plate used for the openEMS vs analytical gate."""
        return cls(
            length=VALIDATION_LENGTH_M,
            width=VALIDATION_WIDTH_M,
            height=VALIDATION_HEIGHT_M,
            epsilon_r=VALIDATION_EPSILON_R,
            z0_ref=DEFAULT_Z0_REF_OHM,
        )
