#!/usr/bin/env python3
"""PDN pipeline entry: Phase 1 plate by default, Phase 2 with --board.

    python run_pipeline.py
    python run_pipeline.py --board boards/pdn_test.kicad_pcb
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from em_extraction import (
    ParallelPlateGeometry,
    analytical_sparams,
    characteristic_impedance,
)
from em_extraction.kicad_reader import read_board
from em_extraction.openems_mesh import openems_available

# Spot-check frequencies (Hz) for the console report — not the FDTD sweep grid.
REPORT_FREQS_HZ = np.array([1e8, 5e8, 1e9])
BOARD_S2P = Path("results") / "board.s2p"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PDN co-simulation pipeline")
    parser.add_argument(
        "--board",
        type=Path,
        help="KiCad .kicad_pcb (Phase 2). Default is the Phase 1 validation plate.",
    )
    parser.add_argument(
        "--decap-index",
        type=int,
        default=0,
        help="Which VCC via to use as port 2 (default: 0, first decap site).",
    )
    args = parser.parse_args(argv)
    if args.board is not None:
        _run_board(args.board, args.decap_index)
        return
    _run_plate()


def _run_plate() -> None:
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


def _run_board(board_path: Path, decap_index: int) -> None:
    board = read_board(board_path)
    gap_m, eps = board.inner_dielectric()
    print(f"Phase 2 — KiCad board {board_path}")
    ox0, oy0 = board.outline_min_m
    ox1, oy1 = board.outline_max_m
    print(
        f"  outline {ox0 * 1e3:.1f}×{oy0 * 1e3:.1f} to {ox1 * 1e3:.1f}×{oy1 * 1e3:.1f} mm  "
        f"PG gap {gap_m * 1e3:.3f} mm  εr={eps}"
    )
    if board.ic_power_pin is None:
        raise SystemExit("no IC power pin (expected footprint U1 pad on net VCC)")
    pin = board.ic_power_pin
    print(
        f"  IC pin U1.{pin.pad} on {pin.net} at "
        f"({pin.x_m * 1e3:.2f}, {pin.y_m * 1e3:.2f}) mm"
    )
    print(f"  {len(board.decap_sites)} VCC via decap site(s):")
    for i, site in enumerate(board.decap_sites):
        mark = " <- port 2" if i == decap_index else ""
        print(f"    [{i}] ({site.x_m * 1e3:.2f}, {site.y_m * 1e3:.2f}) mm{mark}")
    print(flush=True)

    if not openems_available():
        print(
            "openEMS/CSXCAD is not installed. Geometry read succeeded; "
            "install the solver to write results/board.s2p."
        )
        return

    from em_extraction.board_extract import extract_board_sparams

    print(f"Running FDTD (IC pin ↔ decap site {decap_index}) → {BOARD_S2P}", flush=True)
    result = extract_board_sparams(
        board,
        decap_index=decap_index,
        sim_dir=Path("results") / "openems_board",
        output_s2p=BOARD_S2P,
    )
    print("Board S-parameters (spot check in the excite band):")
    print(f"  {'f (MHz)':>10}  {'|S11|':>10}  {'|S21|':>10}  {'|S11|²+|S21|²':>14}")
    for f_want in (0.5e9, 1.0e9, 2.0e9):
        idx = int(np.argmin(np.abs(result.freqs_hz - f_want)))
        s11 = result.s11[idx]
        s21 = result.s21[idx]
        conserv = abs(s11) ** 2 + abs(s21) ** 2
        print(
            f"  {result.freqs_hz[idx] / 1e6:10.1f}  {abs(s11):10.4f}  "
            f"{abs(s21):10.4f}  {conserv:14.4f}"
        )


if __name__ == "__main__":
    main()
