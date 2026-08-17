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

_To be filled in._ BOM cost cap (`cost_budget_usd`).

## Grid

_To be filled in._ Discrete catalog stuffing (count/value), not continuous C.

## Fast plane

_To be filled in._ Cheap cavity/spreading model for placement; not openEMS.
