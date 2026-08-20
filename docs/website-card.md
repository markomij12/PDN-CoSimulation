# PDN Co-Simulation

KiCad board in, decoupling BOM and |Z(f)| out. I started doing this kind of PDN work at Endura; this repo is me rebuilding that pipeline on KiCad, openEMS as a validator, ngspice, and Python. Inner loop is the cavity plane on `pdn_test`, not a GUI.

GitHub: https://github.com/markomij12/PDN-CoSimulation

Suggested images:
- Relative (works now): docs/sample/z_opt.png and docs/sample/pareto.png
- Raw GitHub URLs after public:
  https://raw.githubusercontent.com/markomij12/PDN-CoSimulation/main/docs/sample/z_opt.png
  https://raw.githubusercontent.com/markomij12/PDN-CoSimulation/main/docs/sample/pareto.png

I didn't hit 50 mΩ to 1 GHz (2 nH VRM → ωL ≈ 12.6 Ω at 1 GHz).
