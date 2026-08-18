"""Phase 4 BOM search: no openEMS; skip ngspice / cached .s2p when missing."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from em_extraction.kicad_reader import read_board
from optimizer import optimize_decap_bom
from optimizer.cost import bom_cost, cost_within_budget, unit_price_usd
from optimizer.objective import peak_abs_z
from optimizer.plane import (
    assign_caps_to_sites,
    plane_capacitance,
    plane_impedance,
    spreading_inductance,
)
from optimizer.search import enumerate_count_grid, stuffing_from_counts
from spice_models import ngspice_available
from spice_models.library import (
    DECAP_100N_0402,
    DECAP_1U_0603,
    DECAP_22U_0805,
    DEFAULT_DECAPS,
    DEFAULT_VRM,
    Decap,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_S2P = REPO_ROOT / "results" / "board.s2p"
BOARD_PATH = REPO_ROOT / "boards" / "pdn_test.kicad_pcb"


def _two_of_each() -> tuple[Decap, ...]:
    copies: list[Decap] = []
    for cap in DEFAULT_DECAPS:
        copies.append(cap)
        copies.append(replace(cap, name=f"{cap.name}_1"))
    return tuple(copies)


def _require_ngspice_and_s2p() -> None:
    if not ngspice_available():
        pytest.skip("ngspice not installed")
    if not BOARD_S2P.exists():
        pytest.skip(f"{BOARD_S2P} not generated yet")


# --- Always-run (no ngspice, no .s2p) ---------------------------------------


def test_unit_price_and_bom_cost() -> None:
    assert unit_price_usd(DECAP_100N_0402) == 0.10
    assert unit_price_usd(DECAP_1U_0603) == 0.12
    assert unit_price_usd(DECAP_22U_0805) == 0.20
    assert bom_cost((DECAP_100N_0402,)) == 0.10
    assert bom_cost((DECAP_1U_0603,)) == 0.12
    assert bom_cost((DECAP_22U_0805,)) == 0.20
    assert bom_cost(DEFAULT_DECAPS) == 0.42
    assert bom_cost(_two_of_each()) == 0.84
    assert bom_cost(()) == 0.0


def test_cost_within_budget() -> None:
    assert cost_within_budget(DEFAULT_DECAPS, 0.50) is True
    assert cost_within_budget(_two_of_each(), 0.50) is False


def test_unknown_decap_part_raises() -> None:
    unknown = replace(DECAP_100N_0402, part="not-a-catalog-sku")
    with pytest.raises(ValueError):
        unit_price_usd(unknown)


def test_enumerate_count_grid_default_is_27() -> None:
    candidates = enumerate_count_grid()
    assert len(candidates) == 27
    assert () in candidates


def test_stuffing_from_counts_unique_names() -> None:
    two_100n = stuffing_from_counts((2, 0, 0))
    assert [cap.name for cap in two_100n] == ["C100n", "C100n_1"]
    all_two = stuffing_from_counts((2, 2, 2))
    names = [cap.name for cap in all_two]
    assert len(names) == 6
    assert len(set(names)) == len(names)


def test_peak_abs_z_in_band_and_complex() -> None:
    freq_hz = np.array([1e4, 1e5, 1e6, 1e9, 2e9])
    z_ohm = np.array([1.0, 0.2, 0.5, 0.1, 9.0])
    assert peak_abs_z(z_ohm, freq_hz) == pytest.approx(0.5)

    with pytest.raises(ValueError):
        peak_abs_z(np.array([1.0, 2.0]), np.array([1.0, 10.0]))

    z_complex = np.array([3 + 4j, 0 + 1j])
    assert peak_abs_z(z_complex, np.array([1e5, 1e6])) == pytest.approx(5.0)


def test_fast_plane_no_fdtd() -> None:
    board = read_board(BOARD_PATH)
    assert plane_capacitance(board) == pytest.approx(22.99e-12, rel=0.05)

    empty_sites = tuple(() for _ in board.decap_sites)
    freq_hz, z_empty = plane_impedance(board, empty_sites)
    assert np.all(np.isfinite(z_empty))
    z_100k = float(np.abs(z_empty[np.argmin(np.abs(freq_hz - 1e5))]))
    assert z_100k == pytest.approx(DEFAULT_VRM.r_out_ohm, rel=0.5)
    omega_100k = 2.0 * np.pi * 1e5
    assert z_100k < 0.1 / (omega_100k * plane_capacitance(board))

    _sites, _unused, peak_rich = assign_caps_to_sites(board, DEFAULT_DECAPS)
    peak_empty = float(np.max(np.abs(z_empty)))
    assert np.isfinite(peak_rich)
    assert peak_rich <= peak_empty

    height_m, _eps = board.inner_dielectric()
    l0 = spreading_inductance(0.0, height_m)
    assert np.isfinite(l0)
    assert l0 > 0


def test_optimizer_does_not_import_openems_or_pcbnew() -> None:
    """Fresh interpreter: loading optimizer must not pull CSXCAD/openEMS/pcbnew."""
    import subprocess

    probe = (
        "import optimizer, optimizer.plane, optimizer.search, optimizer.report, sys; "
        "mods = set(sys.modules); "
        "bad = mods & {'CSXCAD', 'openEMS', 'pcbnew'}; "
        "raise SystemExit(0 if not bad else f'imported {bad}')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_optimize_requires_board_path(tmp_path: Path) -> None:
    missing = tmp_path / "nope.s2p"
    with pytest.raises(ValueError, match="boards/pdn_test.kicad_pcb"):
        optimize_decap_bom(missing, results_dir=tmp_path)


def test_optimize_missing_s2p_skips_2port_check(tmp_path: Path) -> None:
    missing = tmp_path / "nope.s2p"
    if not BOARD_PATH.exists():
        pytest.skip(f"{BOARD_PATH} not found")
    result = optimize_decap_bom(
        missing,
        board_path=BOARD_PATH,
        results_dir=tmp_path,
        max_count=1,
    )
    assert np.isfinite(result.peak_z_before_ohm)
    assert np.isfinite(result.peak_z_after_ohm)
    assert result.spice_peak_z_before_ohm is None
    assert result.spice_peak_z_after_ohm is None
    assert result.artifacts["z_png"].is_file()
    assert result.artifacts["bom_txt"].is_file()
    assert "z_2port_png" not in result.artifacts
    assert "droop_png" not in result.artifacts


# --- Skip if ngspice missing OR .s2p missing --------------------------------


def test_optimize_decap_bom_spice_and_plane(tmp_path: Path) -> None:
    _require_ngspice_and_s2p()
    if not BOARD_PATH.exists():
        pytest.skip(f"{BOARD_PATH} not found")

    result = optimize_decap_bom(
        BOARD_S2P,
        max_count=1,
        board_path=BOARD_PATH,
        results_dir=tmp_path,
    )

    assert np.isfinite(result.peak_z_before_ohm)
    assert np.isfinite(result.peak_z_after_ohm)
    assert result.peak_z_after_ohm <= result.peak_z_before_ohm
    assert isinstance(result.stuffing, tuple)
    assert all(isinstance(cap, Decap) for cap in result.stuffing)
    assert result.feasible is True
    assert result.artifacts["z_png"].is_file()
    assert result.artifacts["bom_txt"].is_file()
    assert result.artifacts["z_png"].parent == tmp_path
    assert result.artifacts["bom_txt"].parent == tmp_path
    assert len(result.placement_site_indices) == len(result.stuffing)
    assert result.plane_peak_z_ohm is not None
    assert np.isfinite(result.plane_peak_z_ohm)
    assert result.spice_peak_z_before_ohm is not None
    assert result.spice_peak_z_after_ohm is not None
    assert np.isfinite(result.spice_peak_z_before_ohm)
    assert np.isfinite(result.spice_peak_z_after_ohm)
