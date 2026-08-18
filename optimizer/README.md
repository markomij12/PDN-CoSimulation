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
(equivalent to a 25 mV budget at the Phase 3 0.5 A step). Do not change
this default to make a later plot look like a hit.

50 mΩ to 1 GHz is **not reachable** with `DEFAULT_VRM.l_out_h` = 2 nH:
ωL = 2π f L ≈ 12.6 Ω at 1 GHz (≈ 1.26 Ω at 100 MHz; at 100 kHz ωL ≈ 1.3 mΩ
so the floor is R_out = 10 mΩ). The miss is mostly VRM inductance plus ESL,
not “need more 22 µF”. Do not add catalog SKUs or raise the $0.50 cap to
fake a hit.

`f_cross_hz` is the lowest in-band sample frequency where |Z| > Z_target.
`None` / “met in-band” if no in-band sample violates. `peak_abs_z_freq` is
the frequency of the in-band peak |Z| (lowest f on ties). Both operate on
the caller’s `freq_hz` / `z_ohm` (no re-interpolation).

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

Count/value stuffing at the single extracted 2-port site (Touchstone port 2).
Placement across VCC vias is the Fast plane assignment below, not this grid.

Catalog is `spice_models.library.DEFAULT_DECAPS` in order: `DECAP_100N_0402`,
`DECAP_1U_0603`, `DECAP_22U_0805` (Murata 100 nF 0402, 1 µF 0603, 22 µF 0805).
Each part may appear 0, 1, or 2 times (`MAX_COUNT_PER_PART` = 2) → 3³ = 27
candidates. Repeats get unique SPICE names via
`dataclasses.replace(cap, name=f"{cap.name}_{i}")` with `i` starting at 1,
because `_render_circuit` emits `R{name}` / `L{name}` / `C{name}`. Price still
keys off `Decap.part`. Empty stuffing `(0, 0, 0)` is the before baseline.

The inner loop is `from_sparams` + `simulate_droop` + `peak_abs_z` (ngspice, not
FDTD). Objective is min peak |Z|; the constraint is BOM cost (not `Z_target`
yet). SciPy `minimize` / continuous C is deferred.

## Fast plane

Cheap 1-cavity / spreading model for **placement** after the 2-port count/value
search. Not a mesh, not openEMS, not CSXCAD: a handful of nodes, dense Y, NumPy
`linalg.solve` over frequency. `plane_impedance` does not call ngspice.

Port / site mapping (from `read_board`, never typed by hand):

- Touchstone **port 1** = U1/VCC (`BoardGeometry.ic_power_pin`).
- Decap **sites** = VCC vias (`BoardGeometry.decap_sites`). pdn_test has M = 3.

pdn_test coupon geometry (read from the board, not hardcoded in the model):
30 mm × 20 mm outline, inner gap h = 1.04 mm, εr = 4.5.

Formulas (electrically small below ~1 GHz):

1. Parallel-plate cavity capacitance, lumped at the IC node:

   `C_pp = ε0 * εr * A / h` with `A = (xmax − xmin) * (ymax − ymin)`.

   On pdn_test this is **~23 pF**. `plane_capacitance(board)` exports that value.
   `ε0 = 8.854187817e-12`.

2. Spreading inductance IC → site k:

   `L_k = (μ0 * h / (2π)) * ln(r_k / r_via)`
   with `r_k = hypot(x_k − x_ic, y_k − y_ic)` and `μ0 = 4e-7 * π`.

   `BoardFeature` has no drill. Default `r_via` = **0.15 mm**
   (`DEFAULT_VIA_RADIUS_M`). If `r_k <= r_via`, the ln argument is clamped with
   `max(r_k, r_via * e) / r_via` so `ln >= 1`, `L_k >= μ0 h / 2π` ~ **0.2 nH**,
   and the solve does not produce NaN.

3. Each stuffed MLCC at its site uses the `spice_models` `Decap` R–L–C, not an
   ideal C: `Z_cap = ESR + jω ESL + 1/(jω C)`. Several caps on one via are
   parallel (sum of `1/Z_cap` on that site node).

4. VRM shunt at the IC (`spice_models.library.DEFAULT_VRM`):
   `Z_vrm = R_out + jω L_out` (`R_out` = 10 mΩ, `L_out` = 2 nH). Low-f |Z| is
   ~**10 mΩ**, not `1/ωC → ∞` of a bare cavity.

Nodal stamp (ground implicit): IC node + one node per **used** site. Stamp
`C_pp` and `1/Z_vrm` on the IC; series `1/(jω L_k)` between IC and site k;
`1/Z_cap` on each cap at its site. Drive 1 A into the IC; `Z_ic(f) = V_ic`.
Default frequency grid if the caller omits one: `logspace` 100 kHz–1 GHz,
81 points.

`assign_caps_to_sites` enumerates assignments of each of N caps to one of M
sites (`M^N`; pdn_test M = 3, N typically ≤ 6 → at most 729 NumPy solves).
Empty stuffing is the bare plane+VRM (all sites empty; does not crash). The
winner is the assignment with lowest peak `|Z_ic|`. `optimize_decap_bom` still
selects the BOM with the Part 4 2-port ngspice grid; if `board_path` is set it
then stores `placement_site_indices` (parallel to `stuffing`) and
`plane_peak_z_ohm`. `peak_z_before` / `peak_z_after` stay the 2-port SPICE
numbers — a cached `.s2p` cannot move caps. If `board_path` is None, placement
is left empty (no silent site search).

`plane_z_map` is a coarse peak-|Z| vs xy grid (probe node + spreading L to the
IC, inject at the probe) for the spatial plot. Still not a mesh.

## Artifacts

`--optimize` writes gitignored files under `results/`:

- `z_opt.png` — before/after |Z(f)| (log-log, Z_target line) from a 2-port
  SPICE re-sim of empty vs winning stuffing (check, not the inner loop)
- `droop_opt.png` — before/after IC-pin transient from that same check
- `bom_cost.txt` — part, qty, unit $, ext $
- `z_spatial.png` — fast-plane peak |Z| vs xy when `board_path` is set
  (IC + stuffed/empty VCC vias overlaid; not openEMS)
- `pareto.png` — BOM cost vs plane peak |Z| for each count-vector after
  placement (feasible vs infeasible; winner marked). Fast-plane search,
  not FDTD, not 2-port SPICE. Does not claim Z_target was met.

