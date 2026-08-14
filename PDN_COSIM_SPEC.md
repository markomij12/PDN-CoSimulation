# Project: Automated PDN Co-Simulation & Impedance Optimization Pipeline

## What this is
A Python-driven tool that takes a PCB power delivery network layout, extracts its
electromagnetic parasitics with an open-source 3D field solver, feeds those into a
SPICE transient sim, and automatically optimizes decoupling capacitor placement/values
against a target impedance curve. End to end: **layout → EM extraction → SPICE → optimization → report.**

Portfolio framing: this is the open-source version of what SI/PI teams at AMD, NVIDIA,
Apple, Tesla, and Micron do with HFSS/SIwave + Cadence, built from scratch and scriptable.
Directly extends PDN sim work at Endura — say that explicitly in the README.

## Stack
- Python 3.11+ (NumPy, SciPy, Matplotlib, pandas)
- KiCad 8 — board layout + Python API (`pcbnew` module) for geometry extraction
- openEMS — open-source FDTD 3D EM solver (Python/Octave bindings)
- ngspice (via PySpice or subprocess) — transient SPICE sim. Use ngspice not LTspice
  since it's scriptable/headless and works the same on macOS/Linux.
- Git repo, public, with a real README (not a default one)

## Repo structure
```
pdn-cosim/
├── boards/              # KiCad project(s) — start with one 4-layer test board
├── em_extraction/       # openEMS mesh scripts, port definitions, S-param export
├── spice_models/        # netlist generator, VRM behavioral model, cap library (ESR/ESL)
├── optimizer/           # SciPy-based cap placement/value optimizer
├── results/             # impedance plots, heatmaps, BOM cost tradeoffs
├── tests/                
├── README.md
└── requirements.txt
```

## Build phases (map to weeks, adjust to your actual free time)

### Phase 1 — EM extraction baseline (weeks 1–3)
- Build a simple KiCad 4-layer board: power plane, ground plane, a handful of via
  locations representing decap positions, one "IC" power pin location.
- Write openEMS scripts to mesh this plane pair and extract 2-port S-parameters
  between the IC pin and a candidate decap location.
- **Validation gate:** compare extracted S21/S11 against the analytical parallel-plate
  transmission line formula for the same geometry. If they don't match within a few %,
  don't move on — the mesh/ports are wrong.
- Output: Touchstone (.s2p) files.

### Phase 2 — KiCad → openEMS automation bridge (weeks 3–4)
- Python script using `pcbnew` to read via/pad coordinates and layer stackup directly
  from the .kicad_pcb file — no manual coordinate entry.
- Auto-generate openEMS port definitions from that geometry.
- Goal: change the KiCad layout, rerun one script, get new S-params. No manual steps.

### Phase 3 — SPICE netlist generator + transient sim (weeks 5–6)
- Python module that converts S-parameter blocks into ngspice-compatible equivalent
  circuits (or uses ngspice's native s-param import if available).
- Add a behavioral VRM model (simple averaged buck model is fine — doesn't need to be
  cycle-accurate) and a current step load representing switching digital logic.
- Add real capacitor ESR/ESL parasitics (pull a few real datasheet values, don't use
  ideal caps — this is what makes it credible).
- Run transient sim, extract voltage droop vs. target impedance.

### Phase 4 — Optimization loop (weeks 7–8)
- SciPy optimizer (start with `scipy.optimize.minimize` or a simple grid search before
  anything fancier) that varies cap count/value/placement to minimize peak impedance
  across 100kHz–1GHz subject to a BOM cost constraint.
- Output: before/after impedance vs. frequency plot, voltage droop heatmap across the
  plane, cost table.

### Checkpoint (end of week 8) — decide on fab
You said "not sure yet" on physical fab. Decide here based on how much time is left:
- If ahead of schedule → order the test board (~$30–40, 2–3 week turnaround from JLCPCB),
  measure actual impedance with whatever you have access to (even a cheap VNA/impedance
  analyzer at Penn's EE labs), compare measured vs. simulated. This is the single biggest
  credibility boost you can add — "sim matched measurement within X%" is a killer line.
- If behind schedule → skip it, ship the sim-only version. Still a complete, strong project.

### Phase 5 — Polish (weeks 9–10)
- Write the actual README: problem statement, architecture diagram, how to run it,
  results (plots front and center), what you'd do with more time.
- Push to GitHub, public, clean commit history (not one giant commit).
- One paragraph explicitly connecting this to your Endura PDN work — this is the line
  that makes it a narrative instead of a random project.

## Definition of done
- `python run_pipeline.py` goes from a KiCad board file to a final impedance plot with
  zero manual intervention in between.
- At least one validated comparison point (analytical formula, or measured board if you fab).
- README a recruiter or SI engineer can read in 2 minutes and understand exactly what
  it does and why it's hard.

## Instructions for Cursor
Scaffold the repo structure above. Start with Phase 1 only — don't generate Phase 2-5
code yet. Set up:
1. `requirements.txt` with numpy, scipy, matplotlib, pandas, PySpice
2. A skeleton KiCad-reading script in `em_extraction/` that will later call pcbnew
3. An openEMS mesh script template for a 2-layer test case (simple parallel plate,
   before adding via complexity)
4. A `tests/test_analytical_validation.py` stub that will compare openEMS output to
   the closed-form transmission line impedance formula

Don't stub out Phase 3+ files yet — build incrementally, phase by phase, and validate
each phase before generating the next.
