# Sample `--optimize` run

I ran `python run_pipeline.py --optimize results/board.s2p` on the in-repo coupon `boards/pdn_test.kicad_pcb`. Inner loop is the lumped cavity plane. Missing `.s2p` / ngspice skips the 2-port check; the plane plots still write.

The coupon is a 30 mm × 20 mm 4-layer with VCC/GND on a 0.2 mm inner pair. Two VCC vias sit near U1; one is farther out. Search scores peak |Z| from 100 kHz–30 MHz — that's where these MLCCs can still fight 50 mΩ. Plots still go to 1 GHz.

Peak |Z| in that band went 354 mΩ → 43 mΩ (met in-band). Winner is one 100 nF 0402 + three 1 µF 0603, $0.00 → $0.46 under the $0.50 cap. I still didn't hit 50 mΩ to 1 GHz. Default VRM `L_out` is 2 nH, so ωL ≈ 12.6 Ω at 1 GHz — that's the inductor plus ESL, not "add another 22 µF".

`z_opt.png` is plane Z(f): full band on the left (VRM |R+jωL| overlaid) and the search-band zoom on the right. `pareto.png` is peak Z in the search band vs BOM $. `z_spatial.png` is that same peak vs xy with U1 and vias marked.

`cli.txt` is the captured stdout. `bom_cost.txt` is the qty / unit $ printout.
