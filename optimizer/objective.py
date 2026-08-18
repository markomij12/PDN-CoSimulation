"""Peak |Z(f)| and Z_target crossing over the Phase 4 search band.

Callers pass ``z_ohm`` / ``freq_hz`` they already have (plane ``Z_ic`` or
``DroopResult`` arrays). This module is pure NumPy on those arrays: it does
not re-interpolate, parse wrdata, import ngspice, or import CSXCAD / openEMS
/ pcbnew.
"""

from __future__ import annotations

import numpy as np

# Search band: max |Z(f)| over 100 kHz–1 GHz (Phase 4 spec).
FMIN_HZ = 1e5
FMAX_HZ = 1e9

# Local copy of spice_models.simulate.Z_TARGET_OHM so this module does not
# import simulate.py (ngspice / matplotlib). Matches the z_pdn.png reference
# line. Tighter than 50 mV / 0.5 A = 100 mΩ (equivalent to a 25 mV budget at
# the Phase 3 0.5 A step).
Z_TARGET_OHM = 50e-3


def _in_band_z_and_freq(
    z_ohm: np.ndarray,
    freq_hz: np.ndarray,
    fmin_hz: float,
    fmax_hz: float,
) -> tuple[np.ndarray, np.ndarray]:
    z_ohm = np.asarray(z_ohm)
    freq_hz = np.asarray(freq_hz)
    in_band = (freq_hz >= fmin_hz) & (freq_hz <= fmax_hz)
    if not np.any(in_band):
        raise ValueError(
            f"no |Z(f)| samples in [{fmin_hz:.6g}, {fmax_hz:.6g}] Hz"
        )
    return z_ohm[in_band], freq_hz[in_band]


def peak_abs_z(
    z_ohm: np.ndarray,
    freq_hz: np.ndarray,
    fmin_hz: float = FMIN_HZ,
    fmax_hz: float = FMAX_HZ,
) -> float:
    """Max |Z(f)| over ``fmin_hz``–``fmax_hz`` (inclusive).

    ``z_ohm`` may be complex. Raises ``ValueError`` if no samples fall in-band.
    """
    z_in, _freq = _in_band_z_and_freq(z_ohm, freq_hz, fmin_hz, fmax_hz)
    return float(np.max(np.abs(z_in)))


def peak_abs_z_freq(
    z_ohm: np.ndarray,
    freq_hz: np.ndarray,
    fmin_hz: float = FMIN_HZ,
    fmax_hz: float = FMAX_HZ,
) -> float:
    """Frequency of the in-band peak |Z|. Ties take the lowest frequency.

    ``z_ohm`` may be complex. Raises ``ValueError`` if no samples fall in-band.
    """
    z_in, freq_in = _in_band_z_and_freq(z_ohm, freq_hz, fmin_hz, fmax_hz)
    abs_z = np.abs(z_in)
    return float(np.min(freq_in[abs_z == np.max(abs_z)]))


def f_cross_hz(
    z_ohm: np.ndarray,
    freq_hz: np.ndarray,
    z_target_ohm: float = Z_TARGET_OHM,
    fmin_hz: float = FMIN_HZ,
    fmax_hz: float = FMAX_HZ,
) -> float | None:
    """Lowest in-band sample frequency where |Z| > ``z_target_ohm``.

    ``None`` means no in-band sample violates (met in-band). Does not return
    ``fmax`` as a sentinel. ``z_ohm`` may be complex. Raises ``ValueError`` if
    no samples fall in-band.
    """
    z_in, freq_in = _in_band_z_and_freq(z_ohm, freq_hz, fmin_hz, fmax_hz)
    violators = freq_in[np.abs(z_in) > z_target_ohm]
    if violators.size == 0:
        return None
    return float(np.min(violators))
