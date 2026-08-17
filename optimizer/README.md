# optimizer

Phase 4: search a discrete MLCC BOM to minimize peak |Z(f)| under a cost cap.

This package does **not** import CSXCAD, openEMS, or `pcbnew`, and it does **not**
put FDTD in the inner loop. Cached Touchstone (`.s2p`) in; openEMS remains the
validator. Generate `results/board.s2p` with `python run_pipeline.py --board ...`
first.

## Objective

_To be filled in._ Peak |Z(f)| over the search band.

## Z_target

_To be filled in._ Default matches `spice_models.simulate.Z_TARGET_OHM` (50 mΩ).

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
