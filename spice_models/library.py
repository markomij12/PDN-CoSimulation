"""Behavioral VRM, step-current load, and a handful of real MLCC models.

Capacitors are R–L–C (ESR/ESL), not ideal C. ESL is package-dominated;
ESR is |Z| near self-resonance from the vendor impedance curve. Values are
rounded design numbers, not a substitute for the vendor SPICE model.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# VRM — averaged buck as a Thevenin source. Not cycle-accurate.
# R_out is the closed-loop load-line resistance. L_out is the inductance
# the PDN sees above the voltage-mode loop bandwidth (package + spreading,
# not the full output inductor).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VRM:
    """Thevenin VRM: Vref behind R_out and L_out, attached at the IC node."""

    vref_v: float = 1.0
    r_out_ohm: float = 10e-3
    l_out_h: float = 2e-9


# ---------------------------------------------------------------------------
# Step load at the IC-pin port (Touchstone port 1).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepLoad:
    """PWL current sink: 0 → i_final_a after t_start, rising in t_rise."""

    i_final_a: float = 0.5
    t_start_s: float = 50e-9
    t_rise_s: float = 10e-9
    t_stop_s: float = 2e-6


# ---------------------------------------------------------------------------
# MLCCs. Cite part + why ESR/ESL were chosen; details in spice_models/README.md.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decap:
    """Series R–L–C from a named node to ground."""

    name: str
    part: str
    c_f: float
    esr_ohm: float
    esl_h: float
    case: str
    source: str


# Murata GRM155R71C104KA88: 100 nF, 0402, 16 V, X7R.
# ESL ~ 0.68 nH: package-size typical from TDK Z-curve SRF (see
# https://electronics.stackexchange.com/q/465316 — 0402 ≈ 680 pH).
# ESR ~ 30 mΩ: |Z|min near SRF on Murata SimSurfing for this value/size
# (https://ds.murata.com/simsurfing/mlcc.html).
DECAP_100N_0402 = Decap(
    name="C100n",
    part="Murata GRM155R71C104KA88",
    c_f=100e-9,
    esr_ohm=30e-3,
    esl_h=0.68e-9,
    case="0402",
    source="SimSurfing |Z|min + 0402 ESL≈680 pH",
)

# Murata GRM188R61A105KA61: 1 µF, 0603, 10 V, X5R.
# ESL ~ 0.85 nH (0603 typical, same EE.SE / TDK SRF method).
# ESR ~ 12 mΩ: SimSurfing |Z|min for 1 µF 0603 X5R.
DECAP_1U_0603 = Decap(
    name="C1u",
    part="Murata GRM188R61A105KA61",
    c_f=1e-6,
    esr_ohm=12e-3,
    esl_h=0.85e-9,
    case="0603",
    source="SimSurfing |Z|min + 0603 ESL≈850 pH",
)

# Murata GRM21BR61A226ME51: 22 µF, 0805, 10 V, X5R.
# ESL ~ 1.0 nH (0805 typical; TDK C2012 100 nF SRF ≈ 15.8 MHz → ~1 nH).
# ESR ~ 5 mΩ: SimSurfing |Z|min for 22 µF 0805 X5R.
DECAP_22U_0805 = Decap(
    name="C22u",
    part="Murata GRM21BR61A226ME51",
    c_f=22e-6,
    esr_ohm=5e-3,
    esl_h=1.0e-9,
    case="0805",
    source="SimSurfing |Z|min + 0805 ESL≈1 nH",
)

DEFAULT_VRM = VRM()
DEFAULT_LOAD = StepLoad()
DEFAULT_DECAPS: tuple[Decap, ...] = (DECAP_100N_0402, DECAP_1U_0603, DECAP_22U_0805)
