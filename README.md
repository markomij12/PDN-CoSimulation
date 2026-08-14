# PDN Co-Simulation

Python pipeline for PCB **power delivery network** (PDN) work: take a layout, extract electromagnetic parasitics, run SPICE, and optimize decoupling capacitors against a target impedance curve.

This is the open-source version of what SI/PI teams do with HFSS/SIwave + Cadence. It directly extends PDN simulation work at Endura.

**Status:** Phase 1 scaffold. `python run_pipeline.py` currently evaluates the closed-form parallel-plate model. openEMS extraction is templated and runs once the solver bindings are installed.

## Phase 1 — EM extraction baseline

Validation gate: mesh a **simple parallel-plate pair** in openEMS, extract 2-port S-parameters, and compare S11/S21 to the analytical transmission-line formula. If they disagree by more than a few percent, the mesh or ports are wrong — do not move on.

The plate is a **solver-validation geometry**, not a PDN. A realistic power/ground pair is wide and thin (Z0 ~ 1 Ω); S-parameters against 50 Ω are poorly conditioned and a bad first test. Defaults are a thick, narrower plate (10 mm × 1.6 mm FR-4, Z0 ~ 28 Ω) so the FDTD vs closed-form check is well-conditioned. A 4-layer KiCad test board comes in Phase 2.

## Open question (after the validation gate)

openEMS is FDTD. A PDN impedance sweep from 100 kHz–1 GHz is an awkward time-domain problem: the mesh is set by the smallest feature, the run length by the lowest frequency. Putting FDTD inside an optimizer loop may be too slow. After Phase 1 passes, choose with evidence:

- **openEMS as validator** — FDTD proves mesh/ports; a fast plane model drives optimization.
- **openEMS as extractor** — every layout change re-runs FDTD, likely over a narrower band.

## Stack

- Python 3.11+ (NumPy, SciPy, Matplotlib, pandas, PySpice)
- KiCad 8 (`pcbnew`) — Phase 2
- openEMS / CSXCAD — Phase 1 extractor
- ngspice — later phases

## How to run Phase 1

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py
pytest
```

`pytest` always checks the closed-form Z0. The openEMS vs analytical S-parameter comparison **skips** until `results/parallel_plate.s2p` exists (write it via `extract_sparams(..., output_s2p="results/parallel_plate.s2p")` once openEMS is installed).

## System dependencies

These are **not** pip packages:

- **openEMS + CSXCAD Python bindings** — compiled against the C++ solver; required to run the FDTD template in `em_extraction/openems_mesh.py`.
- **KiCad 8** — Phase 2. `pcbnew` lives in KiCad's bundled Python, not the project venv.
- **ngspice** — later; transient sim via PySpice or subprocess.
