# optimizer

Phase 4: search a discrete MLCC BOM to minimize peak |Z(f)| under a cost cap.

This package does **not** import CSXCAD, openEMS, or `pcbnew`, and it does **not**
put FDTD in the inner loop. Cached Touchstone (`.s2p`) in; openEMS remains the
validator. Generate `results/board.s2p` with `python run_pipeline.py --board ...`
first.

## Objective

Peak |Z(f)| over 100 kHz–1 GHz (`FMIN_HZ` = 1e5, `FMAX_HZ` = 1e9).
`optimizer.objective.peak_abs_z` is pure NumPy on `DroopResult.z_ohm` and
`DroopResult.freq_hz` from `spice_models.simulate_droop` when ngspice is
present — it does not parse wrdata. `z_ohm` may be complex (`np.abs`).
The band mask is inclusive. No in-band samples raises `ValueError`.

## Z_target

Default `Z_TARGET_OHM` = 50 mΩ, defined in `optimizer/objective.py` so the
objective module does not import `spice_models.simulate` (ngspice /
matplotlib). Matches `spice_models.simulate.Z_TARGET_OHM` and the
`z_pdn.png` reference line. Tighter than 50 mV / 0.5 A = 100 mΩ
(equivalent to a 25 mV budget at the Phase 3 0.5 A step).

## Cost

BOM cost cap (`cost_budget_usd`, default `DEFAULT_COST_BUDGET_USD` = $0.50).
Unit prices are qty-1 USD ballparks keyed by `Decap.part` (not object identity),
so `dataclasses.replace` copies still price correctly. Two of each catalog part
is $0.84, so the coupon budget actually trades parts. Empty stuffing costs
$0.00. Unknown `Decap.part` strings raise `ValueError`.

| Constant | Part | Case | Unit USD | Source |
| --- | --- | --- | --- | --- |
| DECAP_100N_0402 | Murata GRM155R71C104KA88 | 0402 | 0.10 | Digi-Key cut-tape qty 1 ballpark for GRM155R71C104KA88J (~₹9.32 / ~$0.10). [GRM155R71C104KA88J](https://www.digikey.com/en/products/detail/murata-electronics/GRM155R71C104KA88J/2610892) |
| DECAP_1U_0603 | Murata GRM188R61A105KA61 | 0603 | 0.12 | Distributor qty-1 ballpark ~$0.12–$0.14 (Mouser/Digi-Key class). Use $0.12. |
| DECAP_22U_0805 | Murata GRM21BR61A226ME51 | 0805 | 0.20 | Digi-Key qty-1 class ~$0.20 (Findchips/Digi-Key range ~$0.20–$0.36 for GRM21BR61A226ME51K). Use $0.20 so a $0.50 coupon budget actually trades parts. |

## Grid

_To be filled in._ Discrete catalog stuffing (count/value), not continuous C.

## Fast plane

_To be filled in._ Cheap cavity/spreading model for placement; not openEMS.
