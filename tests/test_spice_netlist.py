"""Phase 3 netlist generation: no openEMS, skip if cached .s2p is missing."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from em_extraction import ParallelPlateGeometry, analytical_sparams
from em_extraction.sparams import write_touchstone
from spice_models import MissingS2pError, from_sparams

REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_S2P = REPO_ROOT / "results" / "board.s2p"


def _write_plate_s2p(path: Path) -> Path:
    geom = ParallelPlateGeometry.validation_plate()
    freqs = np.linspace(5e8, 8e8, 20)
    write_touchstone(analytical_sparams(geom, freqs), path)
    return path


def test_missing_s2p_tells_you_to_run_board(tmp_path: Path) -> None:
    missing = tmp_path / "nope.s2p"
    with pytest.raises(MissingS2pError, match="--board"):
        from_sparams(missing)


def test_from_sparams_from_analytical_plate(tmp_path: Path) -> None:
    s2p = _write_plate_s2p(tmp_path / "plate.s2p")
    netlist = from_sparams(s2p)
    eq = netlist.equivalent
    assert eq.r_series_ohm > 0
    assert eq.l_series_h > 0
    assert eq.c_ic_f > 0
    assert eq.c_decap_f > 0
    text = netlist.text
    assert netlist.ic_node == "ic"
    assert netlist.decap_node == "decap"
    assert "Vref" in text
    assert "Iload" in text
    assert "RC100n" in text
    assert "0.03" in text  # 100 nF ESR, not ideal C
    assert text.strip().endswith(".end")


def test_from_sparams_board_s2p_when_present() -> None:
    if not BOARD_S2P.exists():
        pytest.skip(f"{BOARD_S2P} not generated yet")
    netlist = from_sparams(BOARD_S2P)
    eq = netlist.equivalent
    assert np.isfinite([eq.r_series_ohm, eq.l_series_h, eq.c_ic_f, eq.c_decap_f]).all()
    assert eq.l_series_h > 0
    assert eq.c_ic_f > 0
    assert "Touchstone port 1 = ic" in netlist.text
    assert "Touchstone port 2 = decap" in netlist.text


def test_spice_models_does_not_import_openems_or_pcbnew() -> None:
    """Fresh interpreter: loading spice_models must not pull CSXCAD/openEMS/pcbnew."""
    import subprocess

    probe = (
        "import spice_models, sys; "
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
