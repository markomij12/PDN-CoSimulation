# Boards

Phase 1 uses a parameterized parallel-plate geometry in `em_extraction.geometry`, not a layout file.

Phase 2 will add a 4-layer KiCad test board here (power plane, ground plane, IC power pin, candidate decap via sites). `em_extraction.kicad_reader.read_board` will parse that `.kicad_pcb` via KiCad's `pcbnew` module.
