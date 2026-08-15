"""Headless ngspice: transient droop + |Z(f)| from a SpiceNetlist.

Uses the ngspice binary via subprocess (not libngspice / PySpice). Callers
never see netlist internals beyond SpiceNetlist / DroopResult.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from spice_models.netlist import SpiceNetlist
from spice_models.ngspice import NgspiceNotInstalledError, ngspice_binary

SETTLE_ABS_V = 5e-3
Z_TARGET_OHM = 50e-3
AC_FMIN_HZ = 1e3
AC_FMAX_HZ = 1e9
AC_PTS_PER_DEC = 51


@dataclass(frozen=True)
class DroopResult:
    """Numeric summary plus artifacts written under results/."""

    time_s: np.ndarray
    v_ic: np.ndarray
    freq_hz: np.ndarray
    z_ohm: np.ndarray
    v_pre_step: float
    v_min: float
    peak_droop_v: float
    t_peak_s: float
    t_settle_s: float | None
    netlist_path: Path
    droop_png: Path
    z_png: Path
    summary_path: Path


def simulate_droop(
    netlist: SpiceNetlist,
    *,
    results_dir: Path | str = Path("results"),
) -> DroopResult:
    """Run .tran and .ac, write droop/|Z| plots, return a numeric summary.

    Raises NgspiceNotInstalledError if the binary is missing. Does not call FDTD.
    """
    ngspice = ngspice_binary()
    out = Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)
    cir_path = out / "pdn.cir"
    log_path = out / "pdn_ngspice.log"
    tran_path = out / "droop_tran.dat"
    ac_path = out / "z_ac.dat"
    cir_path.write_text(_with_analyses(netlist, tran_path, ac_path))

    proc = subprocess.run(
        [str(ngspice), "-b", "-o", str(log_path), str(cir_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    log = log_path.read_text() if log_path.exists() else ""
    if proc.returncode != 0 or not tran_path.exists() or not ac_path.exists():
        detail = (proc.stderr or proc.stdout or log)[-2000:]
        raise RuntimeError(
            f"ngspice failed (exit {proc.returncode}). log={log_path}\n{detail}"
        )

    time_s, v_ic = _read_wrdata_real(tran_path)
    freq_hz, z_ohm = _read_wrdata_complex(ac_path)
    if not np.all(np.isfinite(v_ic)):
        raise RuntimeError("transient v(ic) has non-finite values")
    if not np.all(np.isfinite(z_ohm)):
        raise RuntimeError("AC Z(f) has non-finite values")

    t_start = netlist.load.t_start_s
    pre = time_s < t_start
    if not np.any(pre):
        raise RuntimeError("transient window does not include the pre-step interval")
    v_pre = float(np.median(v_ic[pre]))
    post = time_s >= t_start
    i_min = int(np.argmin(v_ic[post]))
    t_post = time_s[post]
    v_post = v_ic[post]
    v_min = float(v_post[i_min])
    t_peak = float(t_post[i_min])
    peak_droop = v_pre - v_min
    t_settle = _settling_time(time_s, v_ic, t_start)

    droop_png = out / "droop.png"
    z_png = out / "z_pdn.png"
    _plot_droop(time_s, v_ic, v_pre, t_start, t_peak, t_settle, droop_png)
    _plot_z(freq_hz, z_ohm, z_png)

    summary_path = out / "droop_summary.txt"
    summary = _format_summary(netlist, v_pre, v_min, peak_droop, t_peak, t_settle)
    summary_path.write_text(summary + "\n")
    return DroopResult(
        time_s=time_s,
        v_ic=v_ic,
        freq_hz=freq_hz,
        z_ohm=z_ohm,
        v_pre_step=v_pre,
        v_min=v_min,
        peak_droop_v=peak_droop,
        t_peak_s=t_peak,
        t_settle_s=t_settle,
        netlist_path=cir_path,
        droop_png=droop_png,
        z_png=z_png,
        summary_path=summary_path,
    )


def _with_analyses(netlist: SpiceNetlist, tran_path: Path, ac_path: Path) -> str:
    body = netlist.text.rstrip()
    if body.endswith(".end"):
        body = body[: -len(".end")].rstrip()
    tstop = netlist.load.t_stop_s
    tstep = min(0.5e-9, netlist.load.t_rise_s / 20.0)
    ic = netlist.ic_node
    return "\n".join(
        [
            body,
            f"Iac 0 {ic} DC 0 AC 1",
            f".tran {tstep:.6g} {tstop:.6g}",
            f".ac dec {AC_PTS_PER_DEC} {AC_FMIN_HZ:.6g} {AC_FMAX_HZ:.6g}",
            ".control",
            "set filetype=ascii",
            "run",
            "setplot tran1",
            f"wrdata {tran_path} v({ic})",
            "setplot ac1",
            f"wrdata {ac_path} v({ic})",
            "quit",
            ".endc",
            ".end",
            "",
        ]
    )


def _read_wrdata_real(path: Path) -> tuple[np.ndarray, np.ndarray]:
    scale, real, _imag = _read_wrdata(path)
    return scale, real


def _read_wrdata_complex(path: Path) -> tuple[np.ndarray, np.ndarray]:
    scale, real, imag = _read_wrdata(path)
    return scale, real + 1j * imag


def _read_wrdata(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows: list[list[float]] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "*")):
            continue
        rows.append([float(t) for t in line.split()])
    if not rows:
        raise RuntimeError(f"no data in {path}")
    arr = np.asarray(rows, dtype=float)
    if arr.shape[1] < 2:
        raise RuntimeError(f"expected scale + values in {path}, got shape {arr.shape}")
    scale = arr[:, 0]
    real = arr[:, 1]
    imag = arr[:, 2] if arr.shape[1] >= 3 else np.zeros_like(real)
    return scale, real, imag


def _settling_time(time_s: np.ndarray, v_ic: np.ndarray, t_start: float) -> float | None:
    tail = time_s >= (time_s[-1] - 0.1 * (time_s[-1] - time_s[0]))
    v_ss = float(np.median(v_ic[tail]))
    after = time_s >= t_start
    within = np.abs(v_ic - v_ss) <= SETTLE_ABS_V
    # First index after the step where the rest of the waveform stays inside the band.
    idxs = np.flatnonzero(after)
    for i in idxs:
        if np.all(within[i:]):
            return float(time_s[i])
    return None


def _plot_droop(
    time_s: np.ndarray,
    v_ic: np.ndarray,
    v_pre: float,
    t_start: float,
    t_peak: float,
    t_settle: float | None,
    path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.plot(time_s * 1e9, v_ic, color="#1f4e79", lw=1.4, label="v(ic)")
    ax.axhline(v_pre, color="#888888", ls="--", lw=0.8, label=f"pre-step {v_pre:.3f} V")
    ax.axvline(t_start * 1e9, color="#c44", ls=":", lw=0.8, label="load step")
    ax.axvline(t_peak * 1e9, color="#d97706", ls=":", lw=0.8)
    if t_settle is not None:
        ax.axvline(t_settle * 1e9, color="#2a9d8f", ls=":", lw=0.8, label="settled")
    ax.set_xlabel("time (ns)")
    ax.set_ylabel("IC pin voltage (V)")
    ax.set_title("PDN voltage droop (ngspice transient)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _plot_z(freq_hz: np.ndarray, z_ohm: np.ndarray, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.loglog(freq_hz, np.abs(z_ohm), color="#1f4e79", lw=1.4, label="|Z(f)| at IC")
    ax.axhline(Z_TARGET_OHM, color="#c44", ls="--", lw=0.9, label=f"target {Z_TARGET_OHM * 1e3:.0f} mΩ")
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("|Z| (Ω)")
    ax.set_title("PDN impedance at the IC pin (same circuit as droop)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _format_summary(
    netlist: SpiceNetlist,
    v_pre: float,
    v_min: float,
    peak_droop: float,
    t_peak: float,
    t_settle: float | None,
) -> str:
    settle = f"{t_settle * 1e9:.1f} ns" if t_settle is not None else "not within 5 mV by t_stop"
    return "\n".join(
        [
            f"s2p: {netlist.s2p_path}",
            f"Vref: {netlist.vrm.vref_v:.4g} V",
            f"step: {netlist.load.i_final_a:.4g} A",
            f"v_pre_step: {v_pre:.6g} V",
            f"v_min: {v_min:.6g} V",
            f"peak_droop: {peak_droop * 1e3:.3f} mV at t={t_peak * 1e9:.2f} ns",
            f"settling: {settle}",
        ]
    )


# Re-export so tests can skip the same way as ngspice_available.
__all__ = ["DroopResult", "NgspiceNotInstalledError", "simulate_droop"]
