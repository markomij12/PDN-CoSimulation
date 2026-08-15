"""SPICE models for PDN transient: cached Touchstone in, droop out.

Callers pass an existing `.s2p`. This package does not import CSXCAD or openEMS
and must not launch FDTD. Generate or refresh the Touchstone with
`python run_pipeline.py --board ...` first.
"""

from spice_models.library import (
    DECAP_100N_0402,
    DECAP_1U_0603,
    DECAP_22U_0805,
    DEFAULT_DECAPS,
    DEFAULT_LOAD,
    DEFAULT_VRM,
    Decap,
    StepLoad,
    VRM,
)
from spice_models.netlist import (
    MissingS2pError,
    SpiceNetlist,
    TwoPortEquivalent,
    from_sparams,
)
from spice_models.ngspice import NgspiceNotInstalledError, ngspice_available
from spice_models.simulate import DroopResult, simulate_droop

__all__ = [
    "DECAP_100N_0402",
    "DECAP_1U_0603",
    "DECAP_22U_0805",
    "DEFAULT_DECAPS",
    "DEFAULT_LOAD",
    "DEFAULT_VRM",
    "Decap",
    "DroopResult",
    "MissingS2pError",
    "NgspiceNotInstalledError",
    "SpiceNetlist",
    "StepLoad",
    "TwoPortEquivalent",
    "VRM",
    "from_sparams",
    "ngspice_available",
    "simulate_droop",
]
