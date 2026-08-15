"""Locate a headless ngspice binary. Shared-library / PySpice loading is not required."""

from __future__ import annotations

import shutil
from pathlib import Path

# Homebrew on this Mac; also honor a full path if someone sets NGSPICE.
_CANDIDATE_BINS = (
    "ngspice",
    "/opt/homebrew/bin/ngspice",
    "/usr/local/bin/ngspice",
)


class NgspiceNotInstalledError(FileNotFoundError):
    """Raised when the ngspice executable is missing."""


def ngspice_binary() -> Path:
    """Return the ngspice executable path, or raise NgspiceNotInstalledError."""
    for candidate in _CANDIDATE_BINS:
        found = shutil.which(candidate)
        if found:
            return Path(found)
    raise NgspiceNotInstalledError(
        "ngspice not found. On this Mac: brew install ngspice. "
        "Phase 3 tests skip when the binary is missing."
    )


def ngspice_available() -> bool:
    """True when a usable ngspice executable is on PATH or in a Homebrew prefix."""
    try:
        ngspice_binary()
    except NgspiceNotInstalledError:
        return False
    return True
