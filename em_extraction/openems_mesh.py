"""openEMS FDTD mesh/extract template for the parallel-plate validation geometry.

Follows the official openEMS Python lumped-port examples (CSXCAD grid, two
lumped ports, Gaussian excite, `CalcPort` → S-parameters). Bindings are imported
lazily so the rest of the package works without openEMS installed.

See: https://docs.openems.de/python/openEMS.html
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from em_extraction.geometry import ParallelPlateGeometry
from em_extraction.sparams import SParameterResult, write_touchstone

# Band-pass Gauss: f0 > fc so the spectrum excludes DC. A baseband pulse would
# leave electrostatic charge on the plate pair and the energy end-criteria never trips.
F0_HZ = 1.5e9
FC_HZ = 1.0e9
N_FREQS = 401
MAX_TIMESTEPS = 80_000
END_CRITERIA = 1e-4
N_CELLS_ACROSS_GAP = 17
N_CELLS_ALONG_WIDTH = 12
PML_CELLS = 8
PML_CELL_MM = 1.0
PORT_THICKNESS_MM = 0.5


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
        freqs_hz = np.linspace(F0_HZ - FC_HZ, F0_HZ + FC_HZ, N_FREQS)
    else:
        freqs_hz = np.asarray(freqs_hz, dtype=float)

    sim_path = (
        Path(sim_dir).resolve()
        if sim_dir is not None
        else (Path("results") / "openems_parallel_plate").resolve()
    )
    sim_path.mkdir(parents=True, exist_ok=True)

    fdtd, ports = _build_simulation(geom, ContinuousStructure, openEMS)
    # openEMS.Run chdirs into sim_path and then requires cwd == sim_path;
    # a relative path fails that check. Always pass an absolute path.
    cwd = Path.cwd()
    try:
            fdtd.Run(str(sim_path), cleanup=True)
    finally:
        os.chdir(cwd)

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
    """Enclosed parallel-plate waveguide matching Z0 ≈ η h / (w sqrt(εr)).

    Coordinates in mm. Propagation +x, width +y, stack +z.
    PEC on z = the two plates; PMC on y = magnetic walls (no fringing);
    MUR on x = the ports sit on the open ends. No airbox — radiation was
    why |S11|²+|S21|² was far below 1 with the open-plate mesh.
    """
    mm = 1e3
    length = geom.length * mm
    width = geom.width * mm
    height = geom.height * mm
    margin = PML_CELLS * PML_CELL_MM
    port_dx = PORT_THICKNESS_MM
    z_air = margin

    fdtd = openEMS(NrTS=MAX_TIMESTEPS, EndCriteria=END_CRITERIA)
    fdtd.SetGaussExcite(F0_HZ, FC_HZ)
    # PMC on y: no-fringing sidewalls (matches Z0 = η h / w).
    # Explicit plates end at x=0 and x=L; x/z PML absorbs leftover radiation.
    # Do NOT continue the guide into PML — a thin lumped R is otherwise just a bump
    # on an infinite PP waveguide and |S21| stays ~0.4 while energy vanishes in PML.
    fdtd.SetBoundaryCond(["PML_8", "PML_8", "PMC", "PMC", "PML_8", "PML_8"])

    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)

    x0, x1 = 0.0, length
    substrate = csx.AddMaterial("substrate", epsilon=geom.epsilon_r)
    substrate.AddBox([0.0, 0.0, 0.0], [length, width, height], priority=1)

    pec = csx.AddMetal("pec")
    pec.AddBox([0.0, 0.0, 0.0], [length, width, 0.0], priority=10)
    pec.AddBox([0.0, 0.0, height], [length, width, height], priority=10)

    port1 = fdtd.AddLumpedPort(
        1,
        geom.z0_ref,
        [x0, 0.0, 0.0],
        [x0 + port_dx, width, height],
        "z",
        excite=1.0,
        priority=5,
        edges2grid="all",
    )
    port2 = fdtd.AddLumpedPort(
        2,
        geom.z0_ref,
        [x1 - port_dx, 0.0, 0.0],
        [x1, width, height],
        "z",
        excite=0,
        priority=5,
        edges2grid="all",
    )

    n_int = max(12, int(np.ceil(length / max(port_dx, 1.0))))
    mesh.AddLine("x", np.linspace(-margin, 0.0, PML_CELLS + 1))
    mesh.AddLine("x", np.linspace(0.0, length, n_int + 1))
    mesh.AddLine("x", np.linspace(length, length + margin, PML_CELLS + 1))
    mesh.AddLine("y", np.linspace(0.0, width, N_CELLS_ALONG_WIDTH))
    mesh.AddLine("z", np.linspace(-z_air, 0.0, PML_CELLS + 1))
    mesh.AddLine("z", np.linspace(0.0, height, N_CELLS_ACROSS_GAP))
    mesh.AddLine("z", np.linspace(height, height + z_air, PML_CELLS + 1))

    return fdtd, (port1, port2)

    c_mm_per_s = 299792458.0 * mm
    lambda_d = c_mm_per_s / ((F0_HZ + FC_HZ) * np.sqrt(geom.epsilon_r))
    max_res = lambda_d / 20.0
    mesh.SmoothMeshLines("all", max_res, 1.4)

    return fdtd, (port1, port2)
