"""SPICE models for PDN transient: cached Touchstone in, droop out.

Callers pass an existing `.s2p`. This package does not import CSXCAD or openEMS
and must not launch FDTD. Generate or refresh the Touchstone with
`python run_pipeline.py --board ...` first.
"""

from spice_models.ngspice import NgspiceNotInstalledError, ngspice_available

__all__ = [
    "NgspiceNotInstalledError",
    "ngspice_available",
]
