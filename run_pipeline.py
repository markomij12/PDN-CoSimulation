#!/usr/bin/env python3
"""PDN pipeline entry: Phase 1 plate by default; --board / --spice / --optimize.

    python run_pipeline.py
    python run_pipeline.py --board boards/pdn_test.kicad_pcb
    python run_pipeline.py --spice results/board.s2p
    python run_pipeline.py --optimize results/board.s2p
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

# Spot-check frequencies (Hz) for the console report — not the FDTD sweep grid.
REPORT_FREQS_HZ = np.array([1e8, 5e8, 1e9])
BOARD_S2P = Path("results") / "board.s2p"
DEFAULT_BOARD = Path("boards") / "pdn_test.kicad_pcb"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PDN co-simulation pipeline")
    parser.add_argument(
        "--board",
        type=Path,
        help="KiCad .kicad_pcb (Phase 2). Default is the Phase 1 validation plate.",
    )
    parser.add_argument(
        "--spice",
        type=Path,
        help="Cached Touchstone .s2p (Phase 3). Does not run openEMS.",
    )
    parser.add_argument(
        "--optimize",
        type=Path,
        help="Cached Touchstone .s2p (Phase 4 BOM search). Does not run openEMS.",
    )
    parser.add_argument(
        "--decap-index",
        type=int,
        default=0,
        help="Which VCC via to use as port 2 (default: 0, first decap site).",
    )
    args = parser.parse_args(argv)
    chosen = [flag for flag in (args.board, args.spice, args.optimize) if flag is not None]
    if len(chosen) > 1:
        raise SystemExit("use --board, --spice, or --optimize, not more than one")
    if args.optimize is not None:
        _run_optimize(args.optimize)
        return
    if args.spice is not None:
        _run_spice(args.spice)
        return
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

    from em_extraction.openems_mesh import openems_available

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


def _run_spice(s2p_path: Path) -> None:
    from spice_models import MissingS2pError, from_sparams, ngspice_available
    from spice_models.simulate import simulate_droop

    print(f"Phase 3 — SPICE from {s2p_path} (no openEMS)")
    try:
        netlist = from_sparams(s2p_path)
    except MissingS2pError as exc:
        raise SystemExit(str(exc)) from exc

    eq = netlist.equivalent
    print(
        f"  pi: R={eq.r_series_ohm * 1e3:.2f} mΩ  L={eq.l_series_h * 1e9:.3f} nH  "
        f"C_ic={eq.c_ic_f * 1e12:.2f} pF  C_decap={eq.c_decap_f * 1e12:.2f} pF"
    )
    print(
        f"  VRM {netlist.vrm.vref_v:.3g} V + {netlist.vrm.r_out_ohm * 1e3:.3g} mΩ + "
        f"{netlist.vrm.l_out_h * 1e9:.3g} nH; "
        f"step {netlist.load.i_final_a:.3g} A; {len(netlist.decaps)} MLCC(s)"
    )
    if not ngspice_available():
        raise SystemExit(
            "ngspice not found. On this Mac: brew install ngspice. "
            "Then re-run --spice (still does not launch FDTD)."
        )
    result = simulate_droop(netlist)
    print(result.summary_path.read_text().rstrip())
    print(f"  wrote {result.droop_png}  {result.z_png}")


def _run_optimize(s2p_path: Path) -> None:
    from optimizer import optimize_decap_bom
    from spice_models import ngspice_available

    print(f"Phase 4 — optimize decap BOM from {s2p_path} (no openEMS)")
    if not DEFAULT_BOARD.is_file():
        raise SystemExit(
            "boards/pdn_test.kicad_pcb not found. "
            "The plane-scored optimizer needs that KiCad board."
        )
    board_path = DEFAULT_BOARD
    print(f"  placement board {board_path} (fast plane, not FDTD)")
    result = optimize_decap_bom(s2p_path, board_path=board_path)

    names = ", ".join(cap.name for cap in result.stuffing) or "(empty)"
    print(
        f"  peak |Z| {result.peak_z_before_ohm:.4g} Ω → {result.peak_z_after_ohm:.4g} Ω "
        f"(fast plane, 100 kHz–1 GHz); Z_target={result.z_target_ohm * 1e3:.0f} mΩ"
    )
    cross = (
        "met in-band"
        if result.f_cross_hz is None
        else f"f_cross={result.f_cross_hz:.4g} Hz"
    )
    print(
        f"  peak |Z| after at {result.peak_z_after_freq_hz:.4g} Hz; {cross}"
    )
    if (
        result.spice_peak_z_before_ohm is not None
        and result.spice_peak_z_after_ohm is not None
    ):
        print(
            f"  2-port check peak |Z| {result.spice_peak_z_before_ohm:.4g} Ω → "
            f"{result.spice_peak_z_after_ohm:.4g} Ω "
            f"(all MLCCs at extracted site — cannot see other vias)"
        )
    elif not s2p_path.is_file():
        print("  2-port check skipped (missing .s2p; run --board first)")
    elif not ngspice_available():
        print("  2-port check skipped (ngspice not found; brew install ngspice)")
    print(
        f"  BOM ${result.cost_before_usd:.2f} → ${result.cost_after_usd:.2f} "
        f"(budget ${result.cost_budget_usd:.2f}; "
        f"{'feasible' if result.feasible else 'constraint missed'})"
    )
    print(f"  stuffing: {names}")
    if result.placement_site_indices:
        placed = ", ".join(
            f"{cap.name}@via[{i}]"
            for cap, i in zip(result.stuffing, result.placement_site_indices, strict=True)
        )
        plane_z = (
            f"{result.plane_peak_z_ohm:.4g} Ω"
            if result.plane_peak_z_ohm is not None
            else "n/a"
        )
        print(f"  placement: {placed}  (plane peak |Z| {plane_z})")
    wrote = "  ".join(str(path) for path in result.artifacts.values())
    if wrote:
        print(f"  wrote {wrote}")


if __name__ == "__main__":
    main()
