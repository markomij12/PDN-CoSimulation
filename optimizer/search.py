"""Discrete count/value and placement search on the fast cavity plane.

0–2 of each catalog MLCC assigned across ``BoardGeometry.decap_sites``. Does
not import CSXCAD, openEMS, or pcbnew, and does not call FDTD or ngspice.
The inner loop is ``plane_impedance`` / ``peak_abs_z``; cached `.s2p` is not
regenerated per candidate. Repeats get unique ``Decap.name`` values so a
later 2-port SPICE check can emit legal netlist instance names. SciPy /
continuous C is deferred.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

import numpy as np

from em_extraction.kicad_reader import BoardGeometry
from spice_models.library import DEFAULT_DECAPS, Decap

from optimizer.cost import bom_cost, cost_within_budget
from optimizer.objective import peak_abs_z
from optimizer.plane import assign_caps_to_sites, plane_impedance, placement_site_indices

MAX_COUNT_PER_PART = 2
LIBRARY_PARTS: tuple[Decap, ...] = DEFAULT_DECAPS

_EMPTY_COUNTS = (0, 0, 0)
_N_FREQ = 81


@dataclass(frozen=True)
class PlaneGridResult:
    """Winner plus before/after plane peak |Z| and cost. Assembled into OptimizeResult."""

    stuffing: tuple[Decap, ...]
    stuffing_at_sites: tuple[tuple[Decap, ...], ...]
    placement_site_indices: tuple[int, ...]
    peak_z_before_ohm: float
    peak_z_after_ohm: float
    cost_before_usd: float
    cost_after_usd: float
    feasible: bool


def stuffing_from_counts(counts: tuple[int, int, int]) -> tuple[Decap, ...]:
    """Build a stuffing vector from per-part counts in ``LIBRARY_PARTS`` order.

    The first copy of each part keeps the library ``Decap.name``. Repeats use
    ``replace(cap, name=f"{cap.name}_{i}")`` with ``i`` starting at 1 so SPICE
    ``R``/``L``/``C`` instance names stay unique. ``Decap.part`` is unchanged,
    so copies still price correctly.
    """
    stuffing: list[Decap] = []
    for cap, n in zip(LIBRARY_PARTS, counts, strict=True):
        for i in range(n):
            if i == 0:
                stuffing.append(cap)
            else:
                stuffing.append(replace(cap, name=f"{cap.name}_{i}"))
    return tuple(stuffing)


def enumerate_count_grid(
    max_count: int = MAX_COUNT_PER_PART,
) -> list[tuple[Decap, ...]]:
    """All count combinations, including empty ``(0, 0, 0)``. Pure; no ngspice / `.s2p`."""
    n_values = range(max_count + 1)
    return [
        stuffing_from_counts((n0, n1, n2))
        for n0, n1, n2 in itertools.product(n_values, repeat=len(LIBRARY_PARTS))
    ]


def search_plane_grid(
    board: BoardGeometry,
    *,
    cost_budget_usd: float,
    fmin_hz: float,
    fmax_hz: float,
    max_count: int = MAX_COUNT_PER_PART,
) -> PlaneGridResult:
    """Evaluate stuffing × site assignment; pick min plane peak |Z| under the cost cap.

    For each count-grid stuffing, ``assign_caps_to_sites`` enumerates placement
    on ``board.decap_sites``. Score is ``peak_abs_z`` of ``plane_impedance``
    ``Z_ic`` over ``fmin_hz``–``fmax_hz``. Does not call ngspice, FDTD, or
    ``from_sparams``. ``max_count`` defaults to 2 (27 stuffing vectors); tests
    may pass 1 to keep the wall time in seconds.
    """
    empty = stuffing_from_counts(_EMPTY_COUNTS)
    freq_hz = np.logspace(np.log10(fmin_hz), np.log10(fmax_hz), _N_FREQ)
    evaluated: list[
        tuple[
            tuple[Decap, ...],
            float,
            float,
            tuple[tuple[Decap, ...], ...],
            tuple[int, ...],
        ]
    ] = []
    peak_z_before: float | None = None

    for stuffing in enumerate_count_grid(max_count):
        sites, _unused, _assign_peak = assign_caps_to_sites(board, stuffing, freq_hz)
        freq, z_ic = plane_impedance(board, sites, freq_hz)
        peak = peak_abs_z(z_ic, freq, fmin_hz, fmax_hz)
        cost = bom_cost(stuffing)
        indices = placement_site_indices(stuffing, sites)
        evaluated.append((stuffing, peak, cost, sites, indices))
        if stuffing == empty:
            peak_z_before = peak

    if peak_z_before is None:
        raise RuntimeError("count grid did not evaluate the empty stuffing baseline")

    feasible_rows = [
        row for row in evaluated if cost_within_budget(row[0], cost_budget_usd)
    ]
    if feasible_rows:
        winner, peak_after, cost_after, sites_after, indices_after = min(
            feasible_rows, key=lambda row: row[1]
        )
        feasible = True
    else:
        winner, peak_after, cost_after, sites_after, indices_after = min(
            evaluated, key=lambda row: (row[2], row[1])
        )
        feasible = False

    return PlaneGridResult(
        stuffing=winner,
        stuffing_at_sites=sites_after,
        placement_site_indices=indices_after,
        peak_z_before_ohm=peak_z_before,
        peak_z_after_ohm=peak_after,
        cost_before_usd=bom_cost(empty),
        cost_after_usd=cost_after,
        feasible=feasible,
    )
