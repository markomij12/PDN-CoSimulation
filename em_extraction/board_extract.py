"""openEMS 2-port extract for a KiCad power/ground plane pair.

Callers pass `BoardGeometry` (from `read_board`) and get `SParameterResult`.
CSXCAD objects stay inside this module.

Phase 1 lessons reused from `openems_mesh`:
- Band-pass Gauss with f0 > fc (plates are a capacitor; a DC pulse never dies).
- Copper stops at the board outline; PML lives in the xy margin outside the
  planes. Do not continue the plane-pair waveguide into PML.
- `FDTD.Run` gets an absolute `sim_path`; cwd is restored afterwards.
- CSXCAD/openEMS are import-guarded (`OpenEMSNotInstalledError`).

Unlike the validation plate, this mesh uses PML on all xy sides (finite plane,
fringing allowed). PMC sidewalls were only there to match the no-fringing Z0
formula.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from em_extraction.kicad_reader import BoardFeature, BoardGeometry
from em_extraction.openems_mesh import (
    END_CRITERIA,
    F0_HZ,
    FC_HZ,
    MAX_TIMESTEPS,
    N_CELLS_ACROSS_GAP,
    N_FREQS,
    PML_CELL_MM,
    PML_CELLS,
    PORT_THICKNESS_MM,
    OpenEMSNotInstalledError,
    _import_openems,
    openems_available,
)
from em_extraction.sparams import SParameterResult, write_touchstone

DEFAULT_Z0_REF_OHM = 50.0
XY_CELL_MM = 0.5
PORT_HALF_MM = PORT_THICKNESS_MM  # 0.5 mm → 1 mm square clearance around each port


def extract_board_sparams(
    board: BoardGeometry,
    *,
    decap_index: int = 0,
    sim_dir: Path | str | None = None,
    output_s2p: Path | str | None = None,
    freqs_hz: np.ndarray | None = None,
    z0_ref: float = DEFAULT_Z0_REF_OHM,
) -> SParameterResult:
    """2-port S-parameters between the IC power pin and one VCC via (decap site).

    Port 1 is the IC pin; port 2 is `board.decap_sites[decap_index]`.
    """
    if board.ic_power_pin is None:
        raise ValueError("BoardGeometry has no IC power pin (expected U1 pad on VCC)")
    if not board.decap_sites:
        raise ValueError("BoardGeometry has no decap sites (expected vias on VCC)")
    if not 0 <= decap_index < len(board.decap_sites):
        raise IndexError(f"decap_index {decap_index} out of range 0..{len(board.decap_sites) - 1}")

    ContinuousStructure, openEMS = _import_openems()

    if freqs_hz is None:
        freqs_hz = np.linspace(F0_HZ - FC_HZ, F0_HZ + FC_HZ, N_FREQS)
    else:
        freqs_hz = np.asarray(freqs_hz, dtype=float)

    sim_path = (
        Path(sim_dir).resolve()
        if sim_dir is not None
        else (Path("results") / "openems_board").resolve()
    )
    sim_path.mkdir(parents=True, exist_ok=True)

    port_a = board.ic_power_pin
    port_b = board.decap_sites[decap_index]
    fdtd, ports = _build_simulation(board, port_a, port_b, z0_ref, ContinuousStructure, openEMS)

    cwd = Path.cwd()
    try:
        fdtd.Run(str(sim_path), cleanup=True)
    finally:
        os.chdir(cwd)

    for port in ports:
        port.CalcPort(str(sim_path), freqs_hz, ref_impedance=z0_ref)

    s11 = ports[0].uf_ref / ports[0].uf_inc
    s21 = ports[1].uf_ref / ports[0].uf_inc
    result = SParameterResult(
        freqs_hz=freqs_hz,
        s11=np.asarray(s11, dtype=complex),
        s21=np.asarray(s21, dtype=complex),
        s12=np.asarray(s21, dtype=complex),
        s22=np.asarray(s11, dtype=complex),
        z0_ref=z0_ref,
    )
    if output_s2p is not None:
        write_touchstone(result, output_s2p)
    return result


def _build_simulation(
    board: BoardGeometry,
    port_a: BoardFeature,
    port_b: BoardFeature,
    z0_ref: float,
    ContinuousStructure,
    openEMS,
):
    """Mesh the inner plane pair. Coordinates in mm (CSXCAD `SetDeltaUnit(1e-3)`)."""
    mm = 1e3
    height = board.inner_dielectric()[0] * mm
    eps_r = board.inner_dielectric()[1]
    x0 = board.outline_min_m[0] * mm
    y0 = board.outline_min_m[1] * mm
    x1 = board.outline_max_m[0] * mm
    y1 = board.outline_max_m[1] * mm
    margin = PML_CELLS * PML_CELL_MM
    dx = PORT_HALF_MM

    fdtd = openEMS(NrTS=MAX_TIMESTEPS, EndCriteria=END_CRITERIA)
    fdtd.SetGaussExcite(F0_HZ, FC_HZ)
    # Finite plane: radiate in xy (PML), not PMC magnetic walls.
    # z PML sits in air above/below the plates; copper does not enter PML.
    fdtd.SetBoundaryCond(["PML_8", "PML_8", "PML_8", "PML_8", "PML_8", "PML_8"])

    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)

    substrate = csx.AddMaterial("substrate", epsilon=eps_r)
    substrate.AddBox([x0, y0, 0.0], [x1, y1, height], priority=1)

    pec = csx.AddMetal("pec")
    pec.AddBox([x0, y0, 0.0], [x1, y1, 0.0], priority=10)
    pec.AddBox([x0, y0, height], [x1, y1, height], priority=10)

    hole = csx.AddMaterial("port_hole", epsilon=eps_r)
    ports = []
    for port_id, feat, excite in ((1, port_a, 1.0), (2, port_b, 0.0)):
        px = feat.x_m * mm
        py = feat.y_m * mm
        # Punch the PEC at the port so the lumped R is not shorted by copper.
        hole.AddBox([px - dx, py - dx, -0.05], [px + dx, py + dx, 0.05], priority=20)
        hole.AddBox(
            [px - dx, py - dx, height - 0.05],
            [px + dx, py + dx, height + 0.05],
            priority=20,
        )
        ports.append(
            fdtd.AddLumpedPort(
                port_id,
                z0_ref,
                [px - dx, py - dx, 0.0],
                [px + dx, py + dx, height],
                "z",
                excite=excite,
                priority=25,
                edges2grid="all",
            )
        )

    nx = max(8, int(np.ceil((x1 - x0) / XY_CELL_MM)))
    ny = max(8, int(np.ceil((y1 - y0) / XY_CELL_MM)))
    mesh.AddLine("x", np.linspace(x0 - margin, x0, PML_CELLS + 1))
    mesh.AddLine("x", np.linspace(x0, x1, nx + 1))
    mesh.AddLine("x", np.linspace(x1, x1 + margin, PML_CELLS + 1))
    mesh.AddLine("y", np.linspace(y0 - margin, y0, PML_CELLS + 1))
    mesh.AddLine("y", np.linspace(y0, y1, ny + 1))
    mesh.AddLine("y", np.linspace(y1, y1 + margin, PML_CELLS + 1))
    mesh.AddLine("z", np.linspace(-margin, 0.0, PML_CELLS + 1))
    mesh.AddLine("z", np.linspace(0.0, height, N_CELLS_ACROSS_GAP))
    mesh.AddLine("z", np.linspace(height, height + margin, PML_CELLS + 1))

    return fdtd, tuple(ports)


__all__ = [
    "OpenEMSNotInstalledError",
    "extract_board_sparams",
    "openems_available",
]
