# PDN Co-Simulation

KiCad board in, decoupling BOM and impedance plots out.

I extract the power/ground cavity, run SPICE, and search a small catalog of real MLCCs (ESR/ESL, not ideal C) under a cost cap. Same loop SI/PI teams run with HFSS/SIwave and Cadence, minus the GUI.

I started doing this kind of PDN work at Endura. This repo is me rebuilding that pipeline on open tools so I can change a layout and rerun one command.

```
boards/pdn_test.kicad_pcb
        │
        ├── openEMS (validator, run once) → results/board.s2p
        │
        └── fast cavity plane + discrete MLCC grid
                → BOM, via assignment, |Z(f)|, Pareto
                → optional 2-port ngspice check (all caps at port 2)
```

openEMS is how I check the mesh and ports. It is not inside `--optimize`. A 100 kHz–1 GHz PDN sweep is a bad FDTD problem, so the search uses a lumped cavity (plane C + spreading L to each VCC via). `--board` may run FDTD once when the layout changes; `--spice` and `--optimize` do not.

## How to run

```bash
source .venv/bin/activate
python run_pipeline.py                              # Phase 1 plate (analytical gate, not a PDN)
python run_pipeline.py --board boards/pdn_test.kicad_pcb
python run_pipeline.py --spice results/board.s2p
python run_pipeline.py --optimize results/board.s2p  # no FDTD
pytest
```

`--board`, `--spice`, and `--optimize` are mutually exclusive.

macOS: `brew install ngspice`. The pipeline shells out to the `ngspice` binary; you do not need libngspice.

`--optimize` needs `boards/pdn_test.kicad_pcb`. If `results/board.s2p` or ngspice is missing, the plane search still runs and the 2-port check is skipped. If the board is missing, it errors.

Details per command are below. Package notes: `boards/README.md`, `spice_models/README.md`, `optimizer/README.md`.

### Phase 1 — `python run_pipeline.py`

This is a solver check, not a PDN. A real power/ground pair is wide and thin (Z0 ~ 1 Ω); S-parameters against 50 Ω are poorly conditioned, so I use a thicker, narrower plate (10 mm × 1.6 mm FR-4, Z0 ~ 28 Ω). PMC sidewalls, plates stop at the lumped ports.

Default run does not launch FDTD. `pytest` always checks closed-form Z0. When `results/parallel_plate.s2p` exists, |S| has to match the analytical line within 5% in the excite band (0.5–2.5 GHz). If that fails, the mesh or ports are wrong and there is no point continuing.

To regenerate the plate Touchstone (needs openEMS in the venv):

```bash
python -c "from pathlib import Path; from em_extraction import ParallelPlateGeometry; from em_extraction.openems_mesh import extract_sparams; extract_sparams(ParallelPlateGeometry.validation_plate(), sim_dir=Path('results/openems_parallel_plate'), output_s2p=Path('results/parallel_plate.s2p'))"
```

### Phase 2 — `--board boards/pdn_test.kicad_pcb`

Parses the `.kicad_pcb` as text (no `pcbnew`; that module only exists in KiCad's own Python). Reads vias, pads, and stackup, meshes the inner VCC/GND pair, writes `results/board.s2p` (gitignored). Port 1 is `U1` on `VCC`. Port 2 is a VCC via (`--decap-index N` to pick another).

Edit the board in KiCad, save, rerun. No hand-typed coordinates. `boards/README.md` has the net/footprint convention.

### Phase 3 — `--spice results/board.s2p`

Reads the cached `.s2p`, fits a lumped pi, runs ngspice. Does not refresh the Touchstone. If the file is missing, it tells you to run `--board` first.

Writes `results/droop.png`, `results/z_pdn.png`, and a short droop summary. VRM, MLCC RLC, and the pi fit: `spice_models/README.md`.

### Phase 4/5 — `--optimize results/board.s2p`

Inner loop is the plane plus a discrete grid: 0–3 of each of three Murata parts (64 stuffing vectors), assigned to the VCC vias on `pdn_test`. N ≤ 5 enumerates site assignments; more than that is greedy nearest-to-IC. No SciPy `minimize` on C. No openEMS.

The 2-port ngspice pass is a check of the winner with every MLCC at extracted port 2. It cannot see the other vias and it does not pick the BOM.

## Plots

Gitignored. Run `--optimize` and look under `results/`.

| File | What it is |
| --- | --- |
| `z_opt.png` | Plane \|Z(f)\| empty vs winning via assignment. Log-log, 50 mΩ line. |
| `pareto.png` | Peak \|Z\| vs BOM $ for each stuffing after placement. Feasible vs over budget, winner marked. |
| `z_spatial.png` | Plane peak \|Z\| vs xy, IC and vias overlaid. |
| `bom_cost.txt` | Part, qty, unit $, total vs $0.50 budget. |
| `z_opt_2port.png`, `droop_opt.png` | 2-port check only (needs ngspice and `board.s2p`). |

`--spice` still writes `droop.png` and `z_pdn.png` from the `.s2p` alone.

## What this is not

The 2-port `.s2p` cannot move capacitors. Placement is on the plane; the SPICE check parks everything at port 2.

The plane is one cavity: parallel-plate C plus ln spreading L to each used via. Not a full cavity-mode series.

I did not hit 50 mΩ to 1 GHz, and I am not claiming I did. Default VRM `L_out` is 2 nH, so ωL is about 12.6 Ω at 1 GHz (1.26 Ω at 100 MHz). That floor is the inductor plus ESL, not “add another 22 µF”. The search constraint is BOM cost ($0.50). The 50 mΩ line is the same reference as `z_pdn.png`.

`pdn_test` is a 30 mm × 20 mm 4-layer coupon.

## If I had more time

N-port extract so a SPICE check can see more than one via. VNA on a fabbed coupon vs the same `.s2p` / plane. A few more catalog SKUs, still discrete, still cost-capped. None of that is stubbed here.

## Stack

- Python 3.11+ (NumPy, SciPy, Matplotlib, pandas, pytest). PySpice is in `requirements.txt`; runtime is the `ngspice` binary.
- KiCad 8 for the coupon. Geometry comes from the s-expression, not `pcbnew`.
- openEMS / CSXCAD for the Phase 1 plate and Phase 2 `.s2p`.
- ngspice for Phase 3 and the optional optimizer check.

## FDTD install (only if you need `--board` or the plate `.s2p`)

Not pip. On the Mac I used: Homebrew `/opt/homebrew`, openEMS at `~/opt/openEMS`, bindings in this repo's `.venv`.

Rebuild from scratch on a new machine:

```bash
eval "$(/opt/homebrew/bin/brew shellenv)"
brew install cmake pkg-config boost hdf5 cgal vtk
git clone --recursive https://github.com/thliebig/openEMS-Project.git ~/src/openEMS-Project
python3.13 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel cython
pip install -r requirements.txt h5py
export CMAKE_PREFIX_PATH="$(brew --prefix)"
cd ~/src/openEMS-Project
./update_openEMS.sh ~/opt/openEMS --python --disable-GUI
```

`--disable-GUI` skips AppCSXCAD (Qt). TinyXML comes with the script; Homebrew no longer ships it.

KiCad is optional if you only want to edit `boards/pdn_test.kicad_pcb`. `--spice` / `--optimize` do not need a rebuild of openEMS.
