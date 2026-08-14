"""Touchstone helpers and the S-parameter result type used across extractors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

_FREQ_UNIT_TO_HZ = {
    "hz": 1.0,
    "khz": 1e3,
    "mhz": 1e6,
    "ghz": 1e9,
}


@dataclass(frozen=True)
class SParameterResult:
    """2-port S-parameters on a common frequency grid."""

    freqs_hz: np.ndarray
    s11: np.ndarray
    s21: np.ndarray
    s12: np.ndarray
    s22: np.ndarray
    z0_ref: float = 50.0

    def __post_init__(self) -> None:
        n = self.freqs_hz.shape[0]
        for name in ("s11", "s21", "s12", "s22"):
            arr = getattr(self, name)
            if arr.shape != (n,):
                raise ValueError(f"{name} length {arr.shape} != freqs {n}")


def write_touchstone(result: SParameterResult, path: Path | str) -> None:
    """Write a 2-port Touchstone v1 `.s2p` in real/imag form, Hz, R = z0_ref."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "! 2-port S-parameters (RI)",
        f"# Hz S RI R {result.z0_ref:.6g}",
    ]
    for f, s11, s21, s12, s22 in zip(
        result.freqs_hz, result.s11, result.s21, result.s12, result.s22, strict=True
    ):
        lines.append(
            " ".join(
                f"{x:.16e}"
                for x in (
                    float(f),
                    s11.real,
                    s11.imag,
                    s21.real,
                    s21.imag,
                    s12.real,
                    s12.imag,
                    s22.real,
                    s22.imag,
                )
            )
        )
    path.write_text("\n".join(lines) + "\n")


def read_touchstone(path: Path | str) -> SParameterResult:
    """Read a 2-port Touchstone `.s2p` (RI, MA, or DB). Comments (`!`) are ignored."""
    path = Path(path)
    freq_scale = 1.0
    fmt = "ri"
    z0_ref = 50.0
    values: list[float] = []

    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("!"):
            continue
        if line.startswith("#"):
            tokens = line[1:].strip().split()
            if len(tokens) < 3:
                raise ValueError(f"Malformed option line in {path}: {raw}")
            freq_scale = _FREQ_UNIT_TO_HZ[tokens[0].lower()]
            if tokens[1].upper() != "S":
                raise ValueError(f"Only S-parameters are supported, got {tokens[1]}")
            fmt = tokens[2].lower()
            if fmt not in {"ri", "ma", "db"}:
                raise ValueError(f"Unsupported Touchstone format {tokens[2]}")
            if "r" in (t.lower() for t in tokens):
                r_idx = next(i for i, t in enumerate(tokens) if t.lower() == "r")
                z0_ref = float(tokens[r_idx + 1])
            continue
        values.extend(float(t) for t in line.split())

    # 2-port: freq + 8 data values per frequency
    if len(values) % 9 != 0 or not values:
        raise ValueError(f"Expected 9 columns per frequency in {path}, got {len(values)} values")

    rows = np.asarray(values, dtype=float).reshape(-1, 9)
    freqs_hz = rows[:, 0] * freq_scale
    pairs = [(rows[:, i], rows[:, i + 1]) for i in (1, 3, 5, 7)]
    s11, s21, s12, s22 = (_pair_to_complex(a, b, fmt) for a, b in pairs)
    return SParameterResult(
        freqs_hz=freqs_hz,
        s11=s11,
        s21=s21,
        s12=s12,
        s22=s22,
        z0_ref=z0_ref,
    )


def _pair_to_complex(first: np.ndarray, second: np.ndarray, fmt: str) -> np.ndarray:
    if fmt == "ri":
        return first + 1j * second
    if fmt == "ma":
        mag = first
        angle_rad = np.deg2rad(second)
        return mag * np.exp(1j * angle_rad)
    # dB / angle
    mag = 10 ** (first / 20.0)
    angle_rad = np.deg2rad(second)
    return mag * np.exp(1j * angle_rad)
