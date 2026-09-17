# Sample `--optimize` run

I ran `python run_pipeline.py --optimize results/board.s2p` on the in-repo coupon `boards/pdn_test.kicad_pcb`. Inner loop is the lumped cavity plane.

## How to reproduce

`--optimize` does **not** write `results/board.s2p`. That file is gitignored (`results/*`). The 2-port ngspice check reads it if present; otherwise the plane search still runs and the 2-port plots are skipped.

To produce the Touchstone (needs openEMS in the venv; see the root README FDTD install):

```bash
python run_pipeline.py --board boards/pdn_test.kicad_pcb
```

Then, with ngspice on `PATH`:

```bash
python run_pipeline.py --optimize results/board.s2p   # plane plots + 2-port check
python run_pipeline.py --spice results/board.s2p      # z_pdn.png and droop.png only
```

Copy from `results/` into this folder: `cli.txt` (stdout of `--optimize`), `bom_cost.txt`, `z_opt.png`, `pareto.png`, `z_spatial.png`, `z_opt_2port.png`, `droop_opt.png`, `z_pdn.png`, `droop.png`.

Without `--board` / `.s2p`, a clone still gets the plane sample (`z_opt.png`, `pareto.png`, `z_spatial.png`, `bom_cost.txt`). The 2-port and `--spice` images in this folder were generated with a local `results/board.s2p`.

The coupon is a 30 mm × 20 mm 4-layer with VCC/GND on a 0.2 mm inner pair. Two VCC vias sit near U1; one is farther out. Search scores peak |Z| from 100 kHz–30 MHz — that's where these MLCCs can still fight 50 mΩ. Plots still go to 1 GHz.

Peak |Z| in that band went 354 mΩ → 43 mΩ (met in-band). Winner is one 100 nF 0402 + three 1 µF 0603, $0.00 → $0.46 under the $0.50 cap. I still didn't hit 50 mΩ to 1 GHz. Default VRM `L_out` is 2 nH, so ωL ≈ 12.6 Ω at 1 GHz — that's the inductor plus ESL, not "add another 22 µF".

`z_opt.png` is plane Z(f): full band on the left (VRM |R+jωL| overlaid) and the search-band zoom on the right. `pareto.png` is peak Z in the search band vs BOM $. `z_spatial.png` is that same peak vs xy with U1 and vias marked.

`z_opt_2port.png` and `droop_opt.png` are the 2-port check of the winner. Every MLCC is parked at extracted port 2, so that pass can't see the other vias and it doesn't pick the BOM. `z_pdn.png` and `droop.png` are from `--spice` on the same `.s2p`, not the plane.

`cli.txt` is the captured stdout. `bom_cost.txt` is the qty / unit $ printout.
