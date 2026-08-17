"""Discrete count/value grid at the extracted 2-port decap site.

0–2 of each catalog MLCC at Touchstone port 2 (27 stuffing vectors). Does not
import CSXCAD, openEMS, or pcbnew, and does not call FDTD. Cached `.s2p` in;
ngspice evaluates each candidate. Repeats get unique ``Decap.name`` values so
``_render_circuit`` can emit legal SPICE. SciPy / continuous C is deferred.
"""

from __future__ import annotations

import itertools
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from spice_models import Decap, from_sparams, simulate_droop
from spice_models.library import DEFAULT_DECAPS

from optimizer.cost import bom_cost, cost_within_budget
from optimizer.objective import peak_abs_z

MAX_COUNT_PER_PART = 2
LIBRARY_PARTS: tuple[Decap, ...] = DEFAULT_DECAPS

_EMPTY_COUNTS = (0, 0, 0)


@dataclass(frozen=True)
class CountGridResult:
    """Winner plus before/after peak |Z| and cost. Assembled into OptimizeResult."""

    stuffing: tuple[Decap, ...]
    peak_z_before_ohm: float
    peak_z_after_ohm: float
    cost_before_usd: float
    cost_after_usd: float
    feasible: bool


def stuffing_from_counts(counts: tuple[int, int, int]) -> tuple[Decap, ...]:
    """Build a port-2 stuffing vector from per-part counts in ``LIBRARY_PARTS`` order.

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


def search_count_grid(
    s2p_path: Path | str,
    *,
    cost_budget_usd: float,
    fmin_hz: float,
    fmax_hz: float,
    max_count: int = MAX_COUNT_PER_PART,
) -> CountGridResult:
    """Evaluate the count grid; pick min peak |Z| under the cost cap.

    Lets ``from_sparams`` raise ``MissingS2pError`` and ``simulate_droop`` raise
    ``NgspiceNotInstalledError``. Does not call FDTD. Writes ngspice / matplotlib
    scratch under one ``TemporaryDirectory`` so ``results/droop.png`` and
    ``results/z_pdn.png`` are not clobbered. ``max_count`` defaults to 2 (27
    candidates); tests may pass 1 to keep the wall time in seconds.
    """
    empty = stuffing_from_counts(_EMPTY_COUNTS)
    evaluated: list[tuple[tuple[Decap, ...], float, float]] = []
    peak_z_before: float | None = None

    with tempfile.TemporaryDirectory(prefix="pdn_opt_") as scratch:
        scratch_dir = Path(scratch)
        for stuffing in enumerate_count_grid(max_count):
            netlist = from_sparams(s2p_path, decaps=stuffing)
            droop = simulate_droop(netlist, results_dir=scratch_dir)
            peak = peak_abs_z(droop.z_ohm, droop.freq_hz, fmin_hz, fmax_hz)
            cost = bom_cost(stuffing)
            evaluated.append((stuffing, peak, cost))
            if stuffing == empty:
                peak_z_before = peak

    if peak_z_before is None:
        raise RuntimeError("count grid did not evaluate the empty stuffing baseline")

    feasible_rows = [
        row for row in evaluated if cost_within_budget(row[0], cost_budget_usd)
    ]
    if feasible_rows:
        winner, peak_after, cost_after = min(feasible_rows, key=lambda row: row[1])
        feasible = True
    else:
        winner, peak_after, cost_after = min(
            evaluated, key=lambda row: (row[2], row[1])
        )
        feasible = False

    return CountGridResult(
        stuffing=winner,
        peak_z_before_ohm=peak_z_before,
        peak_z_after_ohm=peak_after,
        cost_before_usd=bom_cost(empty),
        cost_after_usd=cost_after,
        feasible=feasible,
    )
