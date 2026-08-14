"""KiCad `.kicad_pcb` reader — implemented in Phase 2.

Do not import `pcbnew` at module level. That module ships inside KiCad's
bundled Python, not a system/venv interpreter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class StackupLayer:
    name: str
    thickness_m: float
    material: str  # "copper" or "dielectric"
    epsilon_r: float | None = None


@dataclass(frozen=True)
class BoardFeature:
    """A pad or via location on the board, in meters, origin = KiCad board origin."""

    x_m: float
    y_m: float
    net: str
    kind: str  # "pad" or "via"


@dataclass(frozen=True)
class BoardGeometry:
    """Layout-derived PDN features. Produced from KiCad in Phase 2."""

    stackup: list[StackupLayer] = field(default_factory=list)
    pads_and_vias: list[BoardFeature] = field(default_factory=list)
    ic_power_pin: BoardFeature | None = None
    decap_sites: list[BoardFeature] = field(default_factory=list)


def read_board(path: Path | str) -> BoardGeometry:
    """Read via/pad coordinates and stackup from a `.kicad_pcb` file.

    Phase 2 will call KiCad's `pcbnew` API (or parse the s-expression file).
    Phase 1 does not use this path — the validation gate is a parameterized plate.
    """
    path = Path(path)
    raise NotImplementedError(
        f"Phase 2: read {path} with pcbnew inside KiCad's Python, not system Python."
    )
