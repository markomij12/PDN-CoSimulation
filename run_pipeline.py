#!/usr/bin/env python3
"""Phase 1 entry point: analytical parallel-plate S-params; openEMS when installed.

Later phases will grow this into: KiCad board → EM extract → SPICE → optimizer → plot.
"""

from __future__ import annotations

import numpy as np

from em_extraction import (
    ParallelPlateGeometry,
    analytical_sparams,
    characteristic_impedance,
)

# Spot-check frequencies (Hz) for the console report — not the FDTD sweep grid.
REPORT_FREQS_HZ = np.array([1e8, 5e8, 1e9])


def main() -> None:
    geom = ParallelPlateGeometry.validation_plate()
    z0 = characteristic_impedance(geom)
    print("Phase 1 — parallel-plate validation geometry (not a PDN plane)")
    print(
        f"  L={geom.length * 1e3:.1f} mm  W={geom.width * 1e3:.1f} mm  "
        f"h={geom.height * 1e3:.2f} mm  εr={geom.epsilon_r}"
    )
    print(f"  Analytical Z0 = {z0:.3f} Ω  (port Zref = {geom.z0_ref:.1f} Ω)")
    print()

    result = analytical_sparams(geom, REPORT_FREQS_HZ)
    print("Analytical S-parameters:")
    print(f"  {'f (MHz)':>10}  {'|S11|':>10}  {'∠S11 (°)':>10}  {'|S21|':>10}  {'∠S21 (°)':>10}")
    for f, s11, s21 in zip(result.freqs_hz, result.s11, result.s21, strict=True):
        print(
            f"  {f / 1e6:10.1f}  {abs(s11):10.4f}  {np.angle(s11, deg=True):10.2f}  "
            f"{abs(s21):10.4f}  {np.angle(s21, deg=True):10.2f}"
        )
    print()

    from em_extraction.openems_mesh import openems_available

    if not openems_available():
        print(
            "openEMS/CSXCAD is not installed. Skipping FDTD extract. "
            "Install the solver, then call extract_sparams(..., "
            "output_s2p='results/parallel_plate.s2p') to un-skip the comparison test."
        )
        return

    print(
        "openEMS bindings found. FDTD is not auto-run from this stub "
        "(long-running). Call em_extraction.openems_mesh.extract_sparams "
        "with output_s2p='results/parallel_plate.s2p' when you are ready."
    )


if __name__ == "__main__":
    main()
