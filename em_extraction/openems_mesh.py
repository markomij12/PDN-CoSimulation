"""openEMS FDTD mesh/extract template for the parallel-plate validation geometry.

Follows the official openEMS Python lumped-port examples (CSXCAD grid, two
lumped ports, Gaussian excite, `CalcPort` → S-parameters). Bindings are imported
lazily so the rest of the package works without openEMS installed.

See: https://docs.openems.de/python/openEMS.html
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from em_extraction.geometry import ParallelPlateGeometry
from em_extraction.sparams import SParameterResult, write_touchstone

# Broadband pulse covering the validation band (hundreds of MHz to a few GHz).
# FDTD is cheap here; 100 kHz PDN sweeps are a later, separate question.
F0_HZ = 1.5e9
FC_HZ = 1.5e9
N_FREQS = 401
METAL_THICKNESS_M = 35e-6  # 1 oz copper, not part of the analytical Z0 model
AIRBOX_MARGIN_M = 10e-3
MAX_TIMESTEPS = 80_000
END_CRITERIA = 1e-4


class OpenEMSNotInstalledError(ImportError):
    """Raised when CSXCAD/openEMS Python bindings are missing."""


def openems_available() -> bool:
    """True when CSXCAD/openEMS can be imported in this interpreter."""
    try:
        _import_openems()
    except OpenEMSNotInstalledError:
        return False
    return True


def extract_sparams(
    geom: ParallelPlateGeometry,
    *,
    sim_dir: Path | str | None = None,
    output_s2p: Path | str | None = None,
    freqs_hz: np.ndarray | None = None,
) -> SParameterResult:
    """Run FDTD on `geom` and return 2-port S-parameters (geometry in, Touchstone out).

    Callers should not touch CSXCAD objects. If `output_s2p` is set, also write `.s2p`.
    """
    ContinuousStructure, openEMS = _import_openems()

    if freqs_hz is None:
        freqs_hz = np.linspace(0.0, 2.0 * F0_HZ, N_FREQS)
    else:
        freqs_hz = np.asarray(freqs_hz, dtype=float)

    sim_path = Path(sim_dir) if sim_dir is not None else Path("results") / "openems_parallel_plate"
    sim_path.mkdir(parents=True, exist_ok=True)

    fdtd, ports = _build_simulation(geom, ContinuousStructure, openEMS)
    fdtd.Run(str(sim_path), cleanup=False)

    for port in ports:
        port.CalcPort(str(sim_path), freqs_hz, ref_impedance=geom.z0_ref)

    # Port 1 excited; port 2 is a matched load (excite=0).
    s11 = ports[0].uf_ref / ports[0].uf_inc
    s21 = ports[1].uf_ref / ports[0].uf_inc
    # Reciprocal, symmetric plate: S12 = S21, S22 = S11 for this lossless 1-D case.
    result = SParameterResult(
        freqs_hz=freqs_hz,
        s11=np.asarray(s11, dtype=complex),
        s21=np.asarray(s21, dtype=complex),
        s12=np.asarray(s21, dtype=complex),
        s22=np.asarray(s11, dtype=complex),
        z0_ref=geom.z0_ref,
    )
    if output_s2p is not None:
        write_touchstone(result, output_s2p)
    return result


def _import_openems():
    try:
        from CSXCAD import ContinuousStructure
        from openEMS import openEMS
    except ImportError as exc:
        raise OpenEMSNotInstalledError(
            "openEMS/CSXCAD Python bindings are not installed. "
            "They are not pip packages — see README System dependencies."
        ) from exc
    return ContinuousStructure, openEMS


def _build_simulation(geom: ParallelPlateGeometry, ContinuousStructure, openEMS):
    """Mesh a parallel-plate pair with lumped ports at x = 0 and x = length.

    Coordinates in mm (CSXCAD `SetDeltaUnit(1e-3)`). Propagation +x, width +y, stack +z.
    """
    mm = 1e3
    length = geom.length * mm
    width = geom.width * mm
    height = geom.height * mm
    metal_t = METAL_THICKNESS_M * mm
    margin = AIRBOX_MARGIN_M * mm

    fdtd = openEMS(NrTS=MAX_TIMESTEPS, EndCriteria=END_CRITERIA)
    fdtd.SetGaussExcite(F0_HZ, FC_HZ)
    fdtd.SetBoundaryCond(["MUR", "MUR", "MUR", "MUR", "MUR", "MUR"])

    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)

    # Dielectric: 0..length, 0..width, 0..height
    substrate = csx.AddMaterial("substrate", epsilon=geom.epsilon_r)
    substrate.AddBox([0.0, 0.0, 0.0], [length, width, height], priority=1)

    pec = csx.AddMetal("pec")
    # Bottom plate slightly into z < 0 so the port spans a well-defined gap.
    pec.AddBox([0.0, 0.0, -metal_t], [length, width, 0.0], priority=10)
    pec.AddBox([0.0, 0.0, height], [length, width, height + metal_t], priority=10)

    # Lumped ports across the dielectric at each end, current in z.
    port1 = fdtd.AddLumpedPort(
        1,
        geom.z0_ref,
        [0.0, 0.0, 0.0],
        [0.0, width, height],
        "z",
        excite=1.0,
        priority=5,
    )
    port2 = fdtd.AddLumpedPort(
        2,
        geom.z0_ref,
        [length, 0.0, 0.0],
        [length, width, height],
        "z",
        excite=0,
        priority=5,
    )

    mesh.AddLine("x", [-margin, 0.0, length, length + margin])
    mesh.AddLine("y", [-margin, 0.0, width, width + margin])
    mesh.AddLine("z", [-margin - metal_t, -metal_t, 0.0, height, height + metal_t, height + metal_t + margin])

    # Resolve ~λ/20 in dielectric at (f0+fc).
    c_mm_per_s = 299792458.0 * mm
    lambda_d = c_mm_per_s / ((F0_HZ + FC_HZ) * np.sqrt(geom.epsilon_r))
    max_res = lambda_d / 20.0
    mesh.SmoothMeshLines("all", max_res, 1.4)

    return fdtd, (port1, port2)
