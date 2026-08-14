"""Public extraction seam: geometry in, S-parameters out."""

from em_extraction.analytical import analytical_sparams, characteristic_impedance
from em_extraction.geometry import ParallelPlateGeometry
from em_extraction.kicad_reader import BoardFeature, BoardGeometry, read_board

__all__ = [
    "BoardFeature",
    "BoardGeometry",
    "ParallelPlateGeometry",
    "analytical_sparams",
    "characteristic_impedance",
    "read_board",
]
