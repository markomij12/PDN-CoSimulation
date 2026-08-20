# Boards

Phase 1 is still the analytical plate in `em_extraction.geometry`, not a layout file.

Phase 2 board: `pdn_test.kicad_pcb` — a small 4-layer FR-4 coupon for the KiCad → openEMS bridge. You don't need the KiCad GUI; `read_board()` parses the s-expression in the project venv.

## `pdn_test.kicad_pcb`

| Item | Value |
| --- | --- |
| Size | 30 mm × 20 mm (`Edge.Cuts` rectangle at the origin) |
| Stackup | 1.6 mm FR-4-ish, 35 µm copper |
| F.Cu / B.Cu | signal (unused by the extractor) |
| In1.Cu | **VCC power plane** |
| In2.Cu | **GND plane** |
| Inner dielectric | 1.04 mm core, εr = 4.5 (the PDN cavity) |
| Prepreg | 0.2 mm, εr = 4.5, F.Cu↔In1.Cu and In2.Cu↔B.Cu |

The `.kicad_pcb` text file stores millimetres (KiCad's *internal* unit is nm). `em_extraction.kicad_reader.read_board` converts millimetres → metres in `BoardGeometry`.

## Net / footprint convention

`read_board()` identifies ports by **names**, not hardcoded xy:

| Role | How it is identified |
| --- | --- |
| Power net | `VCC` |
| Ground net | `GND` |
| IC power pin | footprint reference **`U1`**, pad on net `VCC` |
| Candidate decap sites | vias on net `VCC` |

`U1` is a dummy 2-pin load (pad 1 = VCC, pad 2 = GND). `C1`–`C3` are 0603 placeholders next to the VCC/GND via pairs. Move a VCC via in KiCad and re-run `python run_pipeline.py --board boards/pdn_test.kicad_pcb` to change the extracted S-parameters.

To add another decap candidate, place a via on net `VCC`. To move the IC pin, move footprint `U1`.
