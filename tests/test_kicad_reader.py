"""Unit tests for the KiCad s-expression reader (no openEMS, no pcbnew)."""

from __future__ import annotations

from pathlib import Path

import pytest

from em_extraction.kicad_reader import POWER_NET, read_board

REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = REPO_ROOT / "boards" / "pdn_test.kicad_pcb"

COPPER_THICKNESS_M = 35e-6
INNER_CORE_M = 1.04e-3
INNER_EPS = 4.5
BOARD_WIDTH_M = 30e-3
BOARD_HEIGHT_M = 20e-3


def test_read_board_stackup_thicknesses_in_metres() -> None:
    board = read_board(BOARD_PATH)
    copper = [layer for layer in board.stackup if layer.material == "copper"]
    assert [layer.name for layer in copper] == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    for layer in copper:
        assert layer.thickness_m == pytest.approx(COPPER_THICKNESS_M)

    gap_m, eps = board.inner_dielectric()
    assert gap_m == pytest.approx(INNER_CORE_M)
    assert eps == pytest.approx(INNER_EPS)


def test_read_board_identifies_ic_pin_and_decap_vias_by_name() -> None:
    board = read_board(BOARD_PATH)
    assert board.ic_power_pin is not None
    assert board.ic_power_pin.kind == "pad"
    assert board.ic_power_pin.ref == "U1"
    assert board.ic_power_pin.net == POWER_NET
    assert board.ic_power_pin.pad == "1"

    assert len(board.decap_sites) >= 2
    assert all(site.kind == "via" and site.net == POWER_NET for site in board.decap_sites)


def test_read_board_coordinates_are_metres_not_mm_or_nm() -> None:
    board = read_board(BOARD_PATH)
    assert board.ic_power_pin is not None
    xs = [board.ic_power_pin.x_m, board.ic_power_pin.y_m]
    xs.extend(coord for site in board.decap_sites for coord in (site.x_m, site.y_m))
    for value in xs:
        # 30 mm coupon: metres are ~1e-2. mm-as-m would be ~10; nm-as-m would be ~1e-8.
        assert 1e-4 < abs(value) < 0.1

    assert board.outline_min_m == pytest.approx((0.0, 0.0))
    assert board.outline_max_m[0] == pytest.approx(BOARD_WIDTH_M)
    assert board.outline_max_m[1] == pytest.approx(BOARD_HEIGHT_M)


def test_read_board_u1_pad_matches_footprint_at() -> None:
    board = read_board(BOARD_PATH)
    assert board.ic_power_pin is not None
    # U1 is at (5 mm, 10 mm); pad 1 is at the footprint origin.
    assert board.ic_power_pin.x_m == pytest.approx(5e-3)
    assert board.ic_power_pin.y_m == pytest.approx(10e-3)
