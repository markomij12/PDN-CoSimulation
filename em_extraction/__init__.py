"""Public Phase 1 extraction seam: geometry in, S-parameters out."""

from em_extraction.analytical import analytical_sparams, characteristic_impedance
from em_extraction.geometry import ParallelPlateGeometry

__all__ = [
    "ParallelPlateGeometry",
    "analytical_sparams",
    "characteristic_impedance",
]
