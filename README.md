# PDN Co-Simulation

Python pipeline for PCB **power delivery network** (PDN) work: take a layout, extract electromagnetic parasitics, run SPICE, and optimize decoupling capacitors against a target impedance curve.

This is the open-source version of what SI/PI teams do with HFSS/SIwave + Cadence. It directly extends PDN simulation work at Endura.

**Status:** Phase 1–3 are on this tree. openEMS is the **validator** (mesh/ports), not the inner-loop extractor. Phase 3 is SPICE from cached `.s2p` — it does not launch FDTD.

## Phase 1 — EM extraction baseline

Validation gate: mesh a **simple parallel-plate pair** in openEMS, extract 2-port S-parameters, and compare S11/S21 to the analytical transmission-line formula. If they disagree by more than a few percent, the mesh or ports are wrong — do not move on.

The plate is a **solver-validation geometry**, not a PDN. A realistic power/ground pair is wide and thin (Z0 ~ 1 Ω); S-parameters against 50 Ω are poorly conditioned and a bad first test. Defaults are a thick, narrower plate (10 mm × 1.6 mm FR-4, Z0 ~ 28 Ω) so the FDTD vs closed-form check is well-conditioned. The mesh uses PMC sidewalls (no-fringing, matching the Z0 formula) and stops the plates at the lumped ports so the guide does not continue into PML. A 4-layer KiCad test board is in `boards/pdn_test.kicad_pcb` (Phase 2).

## Decision: openEMS is the validator

FDTD proved the mesh and lumped ports (Phase 1 analytical gate; Phase 2 board power-conservation smoke). A 100 kHz–1 GHz PDN sweep is an awkward time-domain problem, so **do not put openEMS inside the SPICE or optimizer loop**.

- **Phase 3+ consume cached Touchstone** (`results/board.s2p`, regenerated only when the layout changes).
- A fast plane / cavity model can drive later optimization; FDTD remains a spot-check, not the inner loop.
- `python run_pipeline.py` (no `--board`) still does not auto-run FDTD. `--board` may run FDTD once to refresh `.s2p`; SPICE must not.

## Stack

- Python 3.11+ (NumPy, SciPy, Matplotlib, pandas, PySpice)
- KiCad 8 — Phase 2 board files. The pipeline parses `.kicad_pcb` s-expressions in the project venv (`pcbnew` is *not* imported; it only exists in KiCad's bundled Python).
- openEMS / CSXCAD — validator (Phase 1 plate + Phase 2 board `.s2p`), not the SPICE inner loop
- ngspice — Phase 3 transient / AC (`brew install ngspice`). The pipeline shells out to the binary; libngspice / PySpice is not required.

## How to run Phase 1

```bash
cd /Users/markomijatovic/Projects/PDN-CoSimulation
source .venv/bin/activate
python run_pipeline.py
pytest
```

The project venv already has NumPy/SciPy **and** the CSXCAD/openEMS Python extensions (built against `~/opt/openEMS`).

To regenerate `results/parallel_plate.s2p`:

```bash
source .venv/bin/activate
python -c "from pathlib import Path; from em_extraction import ParallelPlateGeometry; from em_extraction.openems_mesh import extract_sparams; extract_sparams(ParallelPlateGeometry.validation_plate(), sim_dir=Path('results/openems_parallel_plate'), output_s2p=Path('results/parallel_plate.s2p'))"
```

`pytest` always checks closed-form Z0. The FDTD vs analytical comparison runs when that `.s2p` exists and requires |S| error < 5% in the excite band.

## How to run Phase 2 (KiCad → openEMS)

Activate the project venv first (it already has CSXCAD/openEMS):

```bash
cd /Users/markomijatovic/Projects/PDN-CoSimulation
source .venv/bin/activate
python run_pipeline.py --board boards/pdn_test.kicad_pcb
pytest
```

That reads via/pad coordinates and stackup from the `.kicad_pcb` (no manual xy), meshes the inner VCC/GND plane pair, and writes `results/board.s2p` (gitignored). Port 1 is footprint `U1` on net `VCC`; port 2 is the first VCC via (`--decap-index N` selects another).

After a layout edit in KiCad, save the board and rerun the same command — no mesh edits.

`pytest` unit-tests the reader against the checked-in board (no solver). The board FDTD smoke (`|S11|²+|S21|² ≈ 1` in the excite band) runs when `results/board.s2p` exists. The Phase 1 analytical gate is unchanged.

Net/footprint conventions are in `boards/README.md`.

## How to run Phase 3 (cached `.s2p` → ngspice)

Activate the project venv. SPICE does **not** run openEMS; it only reads an existing Touchstone.

```bash
cd /Users/markomijatovic/Projects/PDN-CoSimulation
source .venv/bin/activate
python run_pipeline.py --spice results/board.s2p
pytest
```

If `results/board.s2p` is missing, the command tells you to run `--board` first. `--board` is still the way to regenerate `.s2p` after a layout change; `--spice` will not refresh it.

Needs ngspice on PATH:

```bash
brew install ngspice
```

Writes `results/droop.png` (IC-pin voltage vs time), `results/z_pdn.png` (|Z(f)| of the same circuit), and a short numeric summary (peak droop, settling). Port 1 = IC pin, port 2 = decap site. VRM, MLCC ESR/ESL, and the lumped 2-port fit are documented in `spice_models/README.md`.

`pytest` unit-tests netlist generation from the analytical plate (always) and from `results/board.s2p` when that file exists. The transient test skips if ngspice is missing; if ngspice is present it asserts finite voltages and a measurable load-step droop (not a flat rail). Phase 1 and 2 tests are unchanged.

## System dependencies (macOS, Apple Silicon)

These are **not** pip packages. On this Mac they are already installed:

| Piece | Where |
| --- | --- |
| Homebrew | `/opt/homebrew` (`eval "$(/opt/homebrew/bin/brew shellenv)"` is in `~/.zprofile`) |
| cmake, boost, hdf5, cgal, vtk | `brew install cmake boost hdf5 cgal vtk pkg-config` |
| openEMS C++ | `~/opt/openEMS` (`openEMS --help` via `~/opt/openEMS/bin/openEMS`) |
| ngspice | `/opt/homebrew/bin/ngspice` (`brew install ngspice`) |
| Python bindings | project `.venv` (not a pip package) |
| Source tree | `~/src/openEMS-Project` |

Rebuild from scratch (only needed on a new machine):

```bash
eval "$(/opt/homebrew/bin/brew shellenv)"
brew install cmake pkg-config boost hdf5 cgal vtk
git clone --recursive https://github.com/thliebig/openEMS-Project.git ~/src/openEMS-Project
cd /Users/markomijatovic/Projects/PDN-CoSimulation
python3.13 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel cython
pip install -r requirements.txt h5py
export CMAKE_PREFIX_PATH="$(brew --prefix)"
cd ~/src/openEMS-Project
./update_openEMS.sh ~/opt/openEMS --python --disable-GUI
```

`--disable-GUI` skips AppCSXCAD (needs extra Qt). TinyXML is downloaded by the script; Homebrew no longer ships it.

- **KiCad 8** — optional GUI to edit `boards/pdn_test.kicad_pcb`. The pipeline does not call `pcbnew`.
- **ngspice** — `brew install ngspice`. Headless `ngspice -b` for Phase 3; `--spice` does not launch FDTD.
