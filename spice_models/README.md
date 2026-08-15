# spice_models

Phase 3: cached 2-port Touchstone → ngspice netlist → voltage droop and |Z(f)|.

This package does **not** import CSXCAD, openEMS, or `pcbnew`, and it does **not**
launch FDTD. Generate `results/board.s2p` with

```bash
source .venv/bin/activate
python run_pipeline.py --board boards/pdn_test.kicad_pcb
```

then consume it with `--spice`. If the `.s2p` is missing, `from_sparams` fails
and tells you to run `--board` first.

## Port mapping

| Touchstone port | SPICE node | What is attached |
| --- | --- | --- |
| 1 | `ic` | IC power pin: Thevenin VRM + step-current load |
| 2 | `decap` | First VCC via (or `--decap-index N` when the `.s2p` was built): MLCCs |

Ground is node `0`.

## S-parameter → SPICE

The FDTD `.s2p` in this repo starts at 500 MHz and has no DC point. ngspice’s
native Touchstone `file` / `s_xfer` path is AC-only and is unreliable in
transient without DC, so `from_sparams` **fits a lumped pi equivalent** from the
lowest in-band Y-parameters (shunt C at each port, series R+L) and emits that
circuit. Callers do not see the fit; swap the implementation later without
changing the pipeline.

## VRM (averaged buck / Thevenin)

Not cycle-accurate. Default (`spice_models.library.VRM`):

| Symbol | Default | Meaning |
| --- | --- | --- |
| `Vref` | 1.0 V | DC set-point |
| `R_out` | 10 mΩ | closed-loop load-line resistance |
| `L_out` | 2 nH | inductance the PDN sees **above** the voltage-mode loop bandwidth (package + spreading, not the full buck inductor) |

Attached at `ic` as `Vref — R_out — L_out — ic`.

## Step load

Default: 0 → 0.5 A at t = 50 ns, 10 ns rise, PWL current sink from `ic` to ground.
That is a digital-logic current step at the IC-pin port, not a voltage source.

## Decap library (ESR/ESL, not ideal C)

Series R–L–C to ground at `decap`. ESL is package-dominated; ESR is |Z| near
self-resonance from the vendor impedance curve (rounded design values, 25 °C,
0 V bias — not a full DC-bias / temperature model).

| Name | Part | C | ESR | ESL | Sources |
| --- | --- | --- | --- | --- | --- |
| C100n | Murata GRM155R71C104KA88 (0402, 16 V, X7R) | 100 nF | 30 mΩ | 0.68 nH | [Datasheet](https://www.murata.com/); [SimSurfing](https://ds.murata.com/simsurfing/mlcc.html) \|Z\|min; 0402 ESL ≈ 680 pH from TDK Z-curve SRF ([discussion](https://electronics.stackexchange.com/q/465316)) |
| C1u | Murata GRM188R61A105KA61 (0603, 10 V, X5R) | 1 µF | 12 mΩ | 0.85 nH | SimSurfing \|Z\|min; 0603 ESL ≈ 850 pH (same method) |
| C22u | Murata GRM21BR61A226ME51 (0805, 10 V, X5R) | 22 µF | 5 mΩ | 1.0 nH | SimSurfing \|Z\|min; 0805 ESL ≈ 1 nH (TDK C2012 100 nF SRF ≈ 15.8 MHz) |

Murata does not print a single ESR/ESL on the catalog page; they point at
[SimSurfing](https://www.murata.com/en-us/support/faqs/capacitor/ceramiccapacitor/char/0016).
Package ESL is the number that actually sets SRF once the part is mounted.

## How to run

```bash
source .venv/bin/activate
python run_pipeline.py --spice results/board.s2p
```

Needs `ngspice` on PATH (`brew install ngspice` on this Homebrew `/opt/homebrew`
Mac). Plots: `results/droop.png`, `results/z_pdn.png` (gitignored).
