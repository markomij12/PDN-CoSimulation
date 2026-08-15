"""Turn a cached 2-port Touchstone file into an ngspice netlist.

openEMS S-parameters in this repo start at 500 MHz and have no DC point.
ngspice's native Touchstone `file` / `s_xfer` path is AC-only and needs DC
for a reliable operating point, so `from_sparams` fits a lumped pi equivalent
(Y-parameter shunt C at each port, series R+L) from the lowest in-band points
and emits that circuit. Swap the implementation later without changing callers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from em_extraction.sparams import SParameterResult, read_touchstone
from spice_models.library import (
    DEFAULT_DECAPS,
    DEFAULT_LOAD,
    DEFAULT_VRM,
    Decap,
    StepLoad,
    VRM,
)

# Lowest-frequency slice of the FDTD band — lumped pi is only valid electrically short.
_FIT_POINTS = 20
_MIN_SERIES_R_OHM = 1e-3
IC_NODE = "ic"
DECAP_NODE = "decap"


@dataclass(frozen=True)
class TwoPortEquivalent:
    """Lumped pi: shunt C at each port, series R+L between ports."""

    r_series_ohm: float
    l_series_h: float
    c_ic_f: float
    c_decap_f: float
    z0_ref: float
    fit_fmin_hz: float
    fit_fmax_hz: float


@dataclass(frozen=True)
class SpiceNetlist:
    """ngspice deck plus the equivalent that produced it (for tests / plots)."""

    text: str
    s2p_path: Path
    equivalent: TwoPortEquivalent
    vrm: VRM
    load: StepLoad
    decaps: tuple[Decap, ...]
    ic_node: str = IC_NODE
    decap_node: str = DECAP_NODE


class MissingS2pError(FileNotFoundError):
    """Raised when the cached Touchstone is absent — run `--board` first."""


def from_sparams(
    s2p_path: Path | str,
    *,
    vrm: VRM | None = None,
    load: StepLoad | None = None,
    decaps: Sequence[Decap] | None = None,
) -> SpiceNetlist:
    """Load `s2p_path` and return an ngspice netlist for the 2-port PDN.

    Port 1 of the Touchstone is the IC pin (`ic`); port 2 is the decap site
    (`decap`). VRM and the step load sit on port 1; MLCCs sit on port 2.
    Does not run FDTD. Raises MissingS2pError if the file is absent.
    """
    path = Path(s2p_path)
    if not path.is_file():
        raise MissingS2pError(
            f"{path} not found. Run "
            "`python run_pipeline.py --board boards/pdn_test.kicad_pcb` "
            "to generate the cached Touchstone before --spice."
        )
    vrm = vrm if vrm is not None else DEFAULT_VRM
    load = load if load is not None else DEFAULT_LOAD
    caps = tuple(decaps) if decaps is not None else DEFAULT_DECAPS
    result = read_touchstone(path)
    equivalent = fit_pi_equivalent(result)
    text = _render_circuit(path, equivalent, vrm, load, caps)
    return SpiceNetlist(
        text=text,
        s2p_path=path,
        equivalent=equivalent,
        vrm=vrm,
        load=load,
        decaps=caps,
    )


def fit_pi_equivalent(result: SParameterResult) -> TwoPortEquivalent:
    """Fit a passive pi model from the lowest-frequency Y-parameters."""
    n = min(_FIT_POINTS, result.freqs_hz.size)
    if n < 2:
        raise ValueError("need at least two frequency points to fit a pi equivalent")
    freqs = result.freqs_hz[:n]
    y = _s_to_y(
        result.s11[:n],
        result.s21[:n],
        result.s12[:n],
        result.s22[:n],
        result.z0_ref,
    )
    omega = 2.0 * np.pi * freqs
    y_shunt_ic = y[:, 0, 0] + y[:, 0, 1]
    y_series = -y[:, 0, 1]
    y_shunt_decap = y[:, 1, 1] + y[:, 0, 1]
    z_series = 1.0 / y_series

    c_ic = float(np.median(np.real(y_shunt_ic / (1j * omega))))
    c_decap = float(np.median(np.real(y_shunt_decap / (1j * omega))))
    l_series = float(np.median(np.imag(z_series) / omega))
    r_series = float(np.median(np.real(z_series)))
    r_series = max(r_series, _MIN_SERIES_R_OHM)

    if c_ic <= 0 or c_decap <= 0 or l_series <= 0:
        raise ValueError(
            f"pi fit is not passive at the low end of {freqs[0]:.3e}–{freqs[-1]:.3e} Hz: "
            f"C_ic={c_ic:.3e} F  C_decap={c_decap:.3e} F  L={l_series:.3e} H"
        )
    return TwoPortEquivalent(
        r_series_ohm=r_series,
        l_series_h=l_series,
        c_ic_f=c_ic,
        c_decap_f=c_decap,
        z0_ref=float(result.z0_ref),
        fit_fmin_hz=float(freqs[0]),
        fit_fmax_hz=float(freqs[-1]),
    )


def _s_to_y(
    s11: np.ndarray,
    s21: np.ndarray,
    s12: np.ndarray,
    s22: np.ndarray,
    z0: float,
) -> np.ndarray:
    n = s11.shape[0]
    y = np.empty((n, 2, 2), dtype=complex)
    eye = np.eye(2, dtype=complex)
    for i in range(n):
        s = np.array([[s11[i], s12[i]], [s21[i], s22[i]]], dtype=complex)
        y[i] = (eye - s) @ np.linalg.inv(eye + s)
    return y / z0


def _render_circuit(
    s2p_path: Path,
    eq: TwoPortEquivalent,
    vrm: VRM,
    load: StepLoad,
    decaps: tuple[Decap, ...],
) -> str:
    ic = IC_NODE
    decap = DECAP_NODE
    mid = "pdn_ser"
    t0 = load.t_start_s
    t1 = load.t_start_s + load.t_rise_s
    lines = [
        f"* PDN 2-port from {s2p_path}",
        f"* Touchstone port 1 = {ic} (IC pin + VRM + step load)",
        f"* Touchstone port 2 = {decap} (decap site + MLCCs)",
        f"* Pi fit {eq.fit_fmin_hz / 1e6:.1f}–{eq.fit_fmax_hz / 1e6:.1f} MHz  "
        f"Zref={eq.z0_ref:.3g} Ω  (lumped; FDTD band has no DC)",
        "*",
        "* VRM: averaged buck Thevenin (not cycle-accurate)",
        f"Vref vrm_src 0 DC {vrm.vref_v:.6g}",
        f"Rout vrm_src vrm_mid {vrm.r_out_ohm:.6g}",
        f"Lout vrm_mid {ic} {vrm.l_out_h:.6g}",
        "*",
        "* Plane 2-port pi equivalent",
        f"Rser {ic} {mid} {eq.r_series_ohm:.6g}",
        f"Lser {mid} {decap} {eq.l_series_h:.6g}",
        f"Cplane1 {ic} 0 {eq.c_ic_f:.6g}",
        f"Cplane2 {decap} 0 {eq.c_decap_f:.6g}",
        "*",
        f"* Step load at {ic}: 0 → {load.i_final_a:.6g} A",
        f"Iload {ic} 0 PWL(0 0 {t0:.6g} 0 {t1:.6g} {load.i_final_a:.6g} "
        f"{load.t_stop_s:.6g} {load.i_final_a:.6g})",
    ]
    if decaps:
        lines.append("*")
        lines.append(f"* MLCCs at {decap} (ESR/ESL, not ideal C)")
        for cap in decaps:
            esr_n = f"{cap.name}_esr"
            esl_n = f"{cap.name}_esl"
            lines.append(f"* {cap.part} {cap.case}  {cap.source}")
            lines.append(f"R{cap.name} {decap} {esr_n} {cap.esr_ohm:.6g}")
            lines.append(f"L{cap.name} {esr_n} {esl_n} {cap.esl_h:.6g}")
            lines.append(f"C{cap.name} {esl_n} 0 {cap.c_f:.6g}")
    lines.extend([".end", ""])
    return "\n".join(lines)
