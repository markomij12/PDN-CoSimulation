# Sample `--optimize` run

I ran `python run_pipeline.py --optimize results/board.s2p` on the in-repo coupon `boards/pdn_test.kicad_pcb`. The inner loop is the lumped cavity plane, not FDTD. The `.s2p` is only for the optional 2-port ngspice check after the search.

Peak |Z| on the plane went 98.45 Ω → 3.841 Ω (100 kHz–1 GHz). Winner is three 100 nF 0402 + one 1 µF 0603, $0.00 → $0.42 under the $0.50 cap, stuffed as C100n@via[0], C100n_1@via[1], C100n_2@via[2], C1u@via[0]. I didn't hit 50 mΩ. Default VRM `L_out` is 2 nH, so ωL ≈ 12.6 Ω at 1 GHz — that's the inductor plus ESL, not "add another 22 µF". `f_cross` is 2.239 MHz; the in-band peak sits at 1 GHz.

`z_opt.png` is plane Z(f), empty vs that via assignment. `pareto.png` is peak Z vs BOM $ after placement. `z_spatial.png` is plane peak Z vs xy with the IC and vias marked.

`z_opt_2port.png` and `droop_opt.png` are the 2-port check of the winner. Every MLCC is parked at extracted port 2, so that pass can't see the other vias and it doesn't pick the BOM. `z_pdn.png` and `droop.png` are from `--spice` on the same `.s2p`, not the plane.

`cli.txt` is the captured stdout. `bom_cost.txt` is the qty / unit $ printout.
