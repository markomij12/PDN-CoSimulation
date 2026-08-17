"""Peak |Z(f)| over the Phase 4 search band.

Callers pass ``DroopResult.z_ohm`` and ``DroopResult.freq_hz`` from
``spice_models.simulate_droop`` when ngspice is present. This module is
pure NumPy on those arrays: it does not parse wrdata, import ngspice, or
import CSXCAD / openEMS / pcbnew.
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


def peak_abs_z(
    z_ohm: np.ndarray,
    freq_hz: np.ndarray,
    fmin_hz: float = FMIN_HZ,
    fmax_hz: float = FMAX_HZ,
) -> float:
    """Max |Z(f)| over ``fmin_hz``–``fmax_hz`` (inclusive).

    ``z_ohm`` may be complex. Raises ``ValueError`` if no samples fall in-band.
    """
    z_ohm = np.asarray(z_ohm)
    freq_hz = np.asarray(freq_hz)
    in_band = (freq_hz >= fmin_hz) & (freq_hz <= fmax_hz)
    if not np.any(in_band):
        raise ValueError(
            f"no |Z(f)| samples in [{fmin_hz:.6g}, {fmax_hz:.6g}] Hz"
        )
    return float(np.max(np.abs(z_ohm[in_band])))
