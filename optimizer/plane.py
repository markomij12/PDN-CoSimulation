"""Fast 1-cavity / spreading plane model for decap placement.

Electrically small below ~1 GHz: lumped cavity C at the IC, spreading L to
each used VCC via, MLCC R–L–C at the via, VRM shunt at the IC. Tiny dense Y
(IC + used sites), not a mesh. No CSXCAD, openEMS, pcbnew, or ngspice.

Geometry comes from ``BoardGeometry`` (outline, ``inner_dielectric()``, IC pin
xy, decap-site xy). Coordinates are never typed by hand. ``BoardFeature`` has
no drill; spreading uses ``DEFAULT_VIA_RADIUS_M`` = 0.15 mm.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from math import e, hypot, log, pi

import numpy as np

from em_extraction.kicad_reader import BoardGeometry
from spice_models.library import DEFAULT_VRM, Decap

EPS0 = 8.854187817e-12
MU0 = 4e-7 * pi
DEFAULT_VIA_RADIUS_M = 0.15e-3

_FMIN_HZ = 1e5
_FMAX_HZ = 1e9
_N_FREQ = 81


def plane_capacitance(board: BoardGeometry) -> float:
    """Parallel-plate cavity C = ε0 εr A / h from outline and inner dielectric."""
    xmin, ymin = board.outline_min_m
    xmax, ymax = board.outline_max_m
    area_m2 = (xmax - xmin) * (ymax - ymin)
    height_m, eps_r = board.inner_dielectric()
    return EPS0 * eps_r * area_m2 / height_m


def spreading_inductance(
    distance_m: float,
    height_m: float,
    via_radius_m: float = DEFAULT_VIA_RADIUS_M,
) -> float:
    """L = (μ0 h / 2π) ln(r / r_via), clamped so ln >= 1 (no NaN, L >= μ0 h / 2π)."""
    if via_radius_m <= 0:
        raise ValueError("via_radius_m must be positive")
    ratio = max(distance_m, via_radius_m * e) / via_radius_m
    return (MU0 * height_m / (2.0 * pi)) * log(ratio)


def plane_impedance(
    board: BoardGeometry,
    stuffing_at_sites: Sequence[Sequence[Decap]],
    freq_hz: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (freq_hz, z_ic complex). No CSXCAD. No ngspice.

    Drive 1 A into the IC node; ``Z_ic(f) = V_ic``. Ground is implicit.
    """
    freq_hz = _freq_hz(freq_hz)
    omega = 2.0 * np.pi * freq_hz
    y = _admittance_ic_and_sites(board, stuffing_at_sites, omega)
    # Trailing (n, 1) so a 1-node Y is not mistaken for a single (n_freq, 1) RHS.
    current = np.zeros((freq_hz.size, y.shape[-1], 1), dtype=np.complex128)
    current[:, 0, 0] = 1.0
    voltage = np.linalg.solve(y, current)
    return freq_hz, voltage[:, 0, 0]


def plane_z_map(
    board: BoardGeometry,
    stuffing_at_sites: Sequence[Sequence[Decap]],
    freq_hz: np.ndarray | None = None,
    *,
    nx: int = 21,
    ny: int = 15,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Coarse peak-|Z| vs xy.

    For each grid point, add a probe node with spreading L from (x, y) to the
    IC and inject 1 A at the probe; peak |Z| over the band. Used later for the
    spatial plot. No mesh.
    """
    if nx < 1 or ny < 1:
        raise ValueError("nx and ny must be at least 1")
    freq_hz = _freq_hz(freq_hz)
    omega = 2.0 * np.pi * freq_hz
    y_base = _admittance_ic_and_sites(board, stuffing_at_sites, omega)
    ic = _ic_pin(board)
    height_m, _eps_r = board.inner_dielectric()
    xmin, ymin = board.outline_min_m
    xmax, ymax = board.outline_max_m
    x_m = np.linspace(xmin, xmax, nx)
    y_m = np.linspace(ymin, ymax, ny)
    peak_z = np.empty((ny, nx), dtype=float)
    n_base = y_base.shape[-1]
    probe = n_base
    current = np.zeros((freq_hz.size, n_base + 1, 1), dtype=np.complex128)
    current[:, probe, 0] = 1.0
    for iy, y in enumerate(y_m):
        for ix, x in enumerate(x_m):
            y_full = np.zeros(
                (freq_hz.size, n_base + 1, n_base + 1), dtype=np.complex128
            )
            y_full[:, :n_base, :n_base] = y_base
            r_probe = hypot(float(x) - ic.x_m, float(y) - ic.y_m)
            l_probe = spreading_inductance(r_probe, height_m)
            y_l = 1.0 / (1j * omega * l_probe)
            y_full[:, 0, 0] += y_l
            y_full[:, probe, probe] += y_l
            y_full[:, 0, probe] -= y_l
            y_full[:, probe, 0] -= y_l
            v_probe = np.linalg.solve(y_full, current)[:, probe, 0]
            peak_z[iy, ix] = float(np.max(np.abs(v_probe)))
    return x_m, y_m, peak_z


def assign_caps_to_sites(
    board: BoardGeometry,
    stuffing: Sequence[Decap],
    freq_hz: np.ndarray | None = None,
) -> tuple[tuple[tuple[Decap, ...], ...], int, float]:
    """Enumerate assignments of each cap to one of M ``decap_sites`` (M^N).

    Pick the assignment with lowest peak |Z_ic| from ``plane_impedance``.
    Return ``(stuffing_at_sites, unused_site_count, peak_z)``. If stuffing is
    empty, all sites empty and peak |Z| is the bare plane+VRM.
    """
    n_sites = len(board.decap_sites)
    n_caps = len(stuffing)
    if n_caps > 0 and n_sites == 0:
        raise ValueError("BoardGeometry has no decap sites to assign capacitors to")
    freq_hz = _freq_hz(freq_hz)

    best_peak: float | None = None
    best_sites: tuple[tuple[Decap, ...], ...] | None = None
    for assignment in itertools.product(range(n_sites), repeat=n_caps):
        sites = _caps_by_site(stuffing, assignment, n_sites)
        _freq, z_ic = plane_impedance(board, sites, freq_hz)
        peak = float(np.max(np.abs(z_ic)))
        if best_peak is None or peak < best_peak:
            best_peak = peak
            best_sites = sites

    if best_sites is None or best_peak is None:
        raise RuntimeError("cap-to-site enumeration produced no assignments")

    unused = sum(1 for caps in best_sites if len(caps) == 0)
    return best_sites, unused, best_peak


def placement_site_indices(
    stuffing: Sequence[Decap],
    stuffing_at_sites: Sequence[Sequence[Decap]],
) -> tuple[int, ...]:
    """Site index in ``board.decap_sites`` for each cap in ``stuffing`` order."""
    remaining = [list(caps) for caps in stuffing_at_sites]
    indices: list[int] = []
    for cap in stuffing:
        found: int | None = None
        for i, caps in enumerate(remaining):
            for j, other in enumerate(caps):
                if other is cap:
                    found = i
                    del caps[j]
                    break
            if found is not None:
                break
        if found is None:
            raise ValueError("capacitor missing from stuffing_at_sites")
        indices.append(found)
    return tuple(indices)


def _freq_hz(freq_hz: np.ndarray | None) -> np.ndarray:
    if freq_hz is None:
        return np.logspace(np.log10(_FMIN_HZ), np.log10(_FMAX_HZ), _N_FREQ)
    freq = np.asarray(freq_hz, dtype=float).reshape(-1)
    if freq.size == 0:
        raise ValueError("freq_hz is empty")
    return freq


def _ic_pin(board: BoardGeometry):
    if board.ic_power_pin is None:
        raise ValueError("BoardGeometry has no IC power pin (expected U1 pad on VCC)")
    return board.ic_power_pin


def _caps_by_site(
    stuffing: Sequence[Decap],
    assignment: tuple[int, ...],
    n_sites: int,
) -> tuple[tuple[Decap, ...], ...]:
    buckets: list[list[Decap]] = [[] for _ in range(n_sites)]
    for cap, site_i in zip(stuffing, assignment, strict=True):
        buckets[site_i].append(cap)
    return tuple(tuple(caps) for caps in buckets)


def _admittance_ic_and_sites(
    board: BoardGeometry,
    stuffing_at_sites: Sequence[Sequence[Decap]],
    omega: np.ndarray,
) -> np.ndarray:
    """Dense Y(f) for IC + used decap sites. Node 0 is the IC. Ground implicit."""
    if len(stuffing_at_sites) != len(board.decap_sites):
        raise ValueError(
            "stuffing_at_sites length must equal len(board.decap_sites) "
            f"({len(stuffing_at_sites)} != {len(board.decap_sites)})"
        )
    ic = _ic_pin(board)
    height_m, _eps_r = board.inner_dielectric()
    used = [
        (site, caps)
        for site, caps in zip(board.decap_sites, stuffing_at_sites, strict=True)
        if len(caps) > 0
    ]
    n_nodes = 1 + len(used)
    n_freq = omega.size
    y = np.zeros((n_freq, n_nodes, n_nodes), dtype=np.complex128)

    y[:, 0, 0] += 1j * omega * plane_capacitance(board)
    z_vrm = DEFAULT_VRM.r_out_ohm + 1j * omega * DEFAULT_VRM.l_out_h
    y[:, 0, 0] += 1.0 / z_vrm

    for node_i, (site, caps) in enumerate(used, start=1):
        r_k = hypot(site.x_m - ic.x_m, site.y_m - ic.y_m)
        l_k = spreading_inductance(r_k, height_m)
        y_l = 1.0 / (1j * omega * l_k)
        y[:, 0, 0] += y_l
        y[:, node_i, node_i] += y_l
        y[:, 0, node_i] -= y_l
        y[:, node_i, 0] -= y_l
        for cap in caps:
            z_cap = cap.esr_ohm + 1j * omega * cap.esl_h + 1.0 / (1j * omega * cap.c_f)
            y[:, node_i, node_i] += 1.0 / z_cap
    return y
