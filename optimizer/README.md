# optimizer

Phase 4/5: discrete MLCC grid plus via assignment, $0.50 cap, plane peak |Z| as the score.

Inner loop is `search_plane_grid` — cavity plane on `boards/pdn_test.kicad_pcb`. openEMS is the validator, not inside this search. Cached `.s2p` is an optional 2-port check of the winner after the fact; it doesn't pick the BOM. Missing `.s2p` or ngspice skips that check; plane plots still write. Generate `results/board.s2p` with `python run_pipeline.py --board ...` first if you want the check.

This package doesn't import CSXCAD, openEMS, or `pcbnew`.

## Objective

I score peak |Z(f)| over 100 kHz–1 GHz (`FMIN_HZ` = 1e5, `FMAX_HZ` = 1e9). `optimizer.objective.peak_abs_z` is NumPy on the caller's `z_ohm` and `freq_hz` — plane `Z_ic` from `plane_impedance` in the loop, or `DroopResult` arrays from the 2-port check. It doesn't parse wrdata and doesn't need ngspice. `z_ohm` can be complex (`np.abs`). Inclusive band mask. No in-band samples raises `ValueError`.

## Z_target

Default `Z_TARGET_OHM` = 50 mΩ in `optimizer/objective.py` so this module doesn't pull in `spice_models.simulate` (ngspice / matplotlib). Same number as `spice_models.simulate.Z_TARGET_OHM` and the `z_pdn.png` line. Tighter than 50 mV / 0.5 A = 100 mΩ (that's a 25 mV budget at the Phase 3 0.5 A step). Don't change the default to make a plot look like a hit.

I didn't hit 50 mΩ to 1 GHz, and I'm not claiming I did. `DEFAULT_VRM.l_out_h` = 2 nH → ωL ≈ 12.6 Ω at 1 GHz (1.26 Ω at 100 MHz; at 100 kHz ωL ≈ 1.3 mΩ so the floor is R_out = 10 mΩ). That's VRM inductance plus ESL, not "need more 22 µF". Don't add catalog SKUs or raise the $0.50 cap to fake a hit.

`f_cross_hz` is the lowest in-band sample where |Z| > Z_target. `None` / "met in-band" if nothing violates. `peak_abs_z_freq` is the frequency of the in-band peak |Z| (lowest f on ties). Both use the caller's `freq_hz` / `z_ohm` as-is — no re-interpolation. After the search, `optimize_decap_bom` reports `f_cross_hz` / `peak_z_after_freq_hz` from the winner's plane `Z_ic`.

## Cost

BOM cost cap (`cost_budget_usd`, default `DEFAULT_COST_BUDGET_USD` = $0.50). Unit prices are qty-1 USD ballparks keyed by `Decap.part` (not object identity), so `dataclasses.replace` copies still price correctly. Two of each catalog part is $0.84, so the coupon budget actually trades parts. Empty stuffing costs $0.00. Unknown `Decap.part` strings raise `ValueError`.

| Constant | Part | Case | Unit USD | Source |
| --- | --- | --- | --- | --- |
| DECAP_100N_0402 | Murata GRM155R71C104KA88 | 0402 | 0.10 | Digi-Key cut-tape qty 1 ballpark for GRM155R71C104KA88J (~₹9.32 / ~$0.10). [GRM155R71C104KA88J](https://www.digikey.com/en/products/detail/murata-electronics/GRM155R71C104KA88J/2610892) |
| DECAP_1U_0603 | Murata GRM188R61A105KA61 | 0603 | 0.12 | Distributor qty-1 ballpark ~$0.12–$0.14 (Mouser/Digi-Key class). Use $0.12. |
| DECAP_22U_0805 | Murata GRM21BR61A226ME51 | 0805 | 0.20 | Digi-Key qty-1 class ~$0.20 (Findchips/Digi-Key range ~$0.20–$0.36 for GRM21BR61A226ME51K). Use $0.20 so a $0.50 coupon budget actually trades parts. |

## Grid

Count/value stuffing of the three catalog parts. Placement across VCC vias is `search_plane_grid` → `assign_caps_to_sites`.

Catalog is `spice_models.library.DEFAULT_DECAPS` in order: `DECAP_100N_0402`, `DECAP_1U_0603`, `DECAP_22U_0805` (Murata 100 nF 0402, 1 µF 0603, 22 µF 0805). Each part may appear 0–3 times (`MAX_COUNT_PER_PART` = 3) → 4³ = 64 candidates. Repeats get unique SPICE names via `dataclasses.replace(cap, name=f"{cap.name}_{i}")` with `i` starting at 1, because `_render_circuit` emits `R{name}` / `L{name}` / `C{name}` in the optional 2-port check. Price still keys off `Decap.part`. Empty stuffing `(0, 0, 0)` is the before baseline.

`search_plane_grid` walks `enumerate_count_grid` (0–3 each, 64 vectors) × `assign_caps_to_sites` (enumerate N ≤ 5, greedy nearest-to-IC if larger), scored by `plane_impedance` / `peak_abs_z`. No SciPy `minimize` on C. Objective is min plane peak |Z|; the constraint is BOM cost (not `Z_target` yet).

## Fast plane

Cheap 1-cavity / spreading model for count/value and placement (`search_plane_grid`). A handful of nodes, dense Y, NumPy `linalg.solve` over frequency — not a mesh. `plane_impedance` doesn't call ngspice.

Port / site mapping comes from `read_board`, never typed by hand:

- Touchstone **port 1** = U1/VCC (`BoardGeometry.ic_power_pin`).
- Decap **sites** = VCC vias (`BoardGeometry.decap_sites`). pdn_test has M = 3.

pdn_test coupon (read from the board, not hardcoded in the model): 30 mm × 20 mm outline, inner gap h = 1.04 mm, εr = 4.5.

Formulas (electrically small below ~1 GHz):

1. Parallel-plate cavity capacitance, lumped at the IC node:

   `C_pp = ε0 * εr * A / h` with `A = (xmax − xmin) * (ymax − ymin)`.

   On pdn_test this is **~23 pF**. `plane_capacitance(board)` exports that value. `ε0 = 8.854187817e-12`.

2. Spreading inductance IC → site k:

   `L_k = (μ0 * h / (2π)) * ln(r_k / r_via)`
   with `r_k = hypot(x_k − x_ic, y_k − y_ic)` and `μ0 = 4e-7 * π`.

   `BoardFeature` has no drill. Default `r_via` = **0.15 mm** (`DEFAULT_VIA_RADIUS_M`). If `r_k <= r_via`, the ln argument is clamped with `max(r_k, r_via * e) / r_via` so `ln >= 1`, `L_k >= μ0 h / 2π` ~ **0.2 nH**, and the solve doesn't produce NaN.

3. Each stuffed MLCC at its site uses the `spice_models` `Decap` R–L–C, not an ideal C: `Z_cap = ESR + jω ESL + 1/(jω C)`. Several caps on one via are parallel (sum of `1/Z_cap` on that site node).

4. VRM shunt at the IC (`spice_models.library.DEFAULT_VRM`): `Z_vrm = R_out + jω L_out` (`R_out` = 10 mΩ, `L_out` = 2 nH). Low-f |Z| is ~**10 mΩ**, not `1/ωC → ∞` of a bare cavity.

Nodal stamp (ground implicit): IC node + one node per **used** site. Stamp `C_pp` and `1/Z_vrm` on the IC; series `1/(jω L_k)` between IC and site k; `1/Z_cap` on each cap at its site. Drive 1 A into the IC; `Z_ic(f) = V_ic`. Default frequency grid if the caller omits one: `logspace` 100 kHz–1 GHz, 81 points.

`assign_caps_to_sites` enumerates assignments of each of N caps to one of M sites when N ≤ 5 (`ENUMERATE_MAX_CAPS`; `M^N`; pdn_test M = 3 → at most 3^5 = 243 NumPy solves). For N > 5 it uses a deterministic greedy: sites sorted nearest-to-IC, first `min(N, M)` caps each get the next unused via, leftover caps share the nearest via. Empty stuffing is the bare plane+VRM (all sites empty; doesn't crash). The winner is the assignment with lowest peak `|Z_ic|` (greedy scores that single assignment).

`optimize_decap_bom` **requires** `board_path` (`boards/pdn_test.kicad_pcb`) and doesn't silently skip placement. It selects the BOM with `search_plane_grid`. `peak_z_before_ohm` / `peak_z_after_ohm` are **plane** numbers. `spice_peak_z_*` are the optional 2-port check (`None` if `.s2p` or ngspice is missing). `f_cross_hz` / `peak_z_after_freq_hz` come from the winner's plane `Z_ic`. The 2-port check parks all MLCCs at extracted port 2; it can't see other vias and doesn't pick the winner.

`plane_z_map` is a coarse peak-|Z| vs xy grid (probe node + spreading L to the IC, inject at the probe) for the spatial plot. Still not a mesh.

## Artifacts

`--optimize` writes gitignored files under `results/`:

- `z_opt.png` — before/after plane |Z(f)| (log-log, Z_target line) from empty sites vs winning via assignment (`plane_impedance`).
- `pareto.png` — BOM cost vs plane peak |Z| for each count-vector after placement (feasible vs infeasible; winner marked). Doesn't claim Z_target was met.
- `z_spatial.png` — plane peak |Z| vs xy (IC + stuffed/empty VCC vias overlaid).
- `bom_cost.txt` — part, qty, unit $, ext $
- `z_opt_2port.png` / `droop_opt.png` — 2-port check only, and only if ngspice and a cached `.s2p` are both present. All caps at the extracted site. Not written when the check is skipped.
