"""Qty-1 USD ballparks and BOM cost for the discrete MLCC catalog.

Prices are keyed by ``Decap.part`` so ``dataclasses.replace`` copies still
price correctly. This module does not import CSXCAD, openEMS, or pcbnew.
"""

from __future__ import annotations

from collections.abc import Sequence

from spice_models.library import (
    DECAP_100N_0402,
    DECAP_1U_0603,
    DECAP_22U_0805,
    Decap,
)

# Coupon: 2 of each catalog part = $0.84, so the cap actually bites.
DEFAULT_COST_BUDGET_USD = 0.50

# Murata GRM155R71C104KA88: 100 nF, 0402.
# Digi-Key cut-tape qty 1 ballpark for GRM155R71C104KA88J (~₹9.32 / ~$0.10).
# https://www.digikey.com/en/products/detail/murata-electronics/GRM155R71C104KA88J/2610892
_PRICE_100N_0402_USD = 0.10

# Murata GRM188R61A105KA61: 1 µF, 0603.
# Distributor qty-1 ballpark ~$0.12–$0.14 (Mouser/Digi-Key class). Use $0.12.
_PRICE_1U_0603_USD = 0.12

# Murata GRM21BR61A226ME51: 22 µF, 0805.
# Digi-Key qty-1 class ~$0.20 (Findchips/Digi-Key range ~$0.20–$0.36 for
# GRM21BR61A226ME51K). Use $0.20 so a $0.50 coupon budget actually trades parts.
_PRICE_22U_0805_USD = 0.20

_UNIT_PRICE_USD: dict[str, float] = {
    DECAP_100N_0402.part: _PRICE_100N_0402_USD,
    DECAP_1U_0603.part: _PRICE_1U_0603_USD,
    DECAP_22U_0805.part: _PRICE_22U_0805_USD,
}


def unit_price_usd(cap: Decap) -> float:
    """Qty-1 USD ballpark for a library MLCC, keyed by ``cap.part``."""
    try:
        return _UNIT_PRICE_USD[cap.part]
    except KeyError:
        raise ValueError(f"unknown decap part: {cap.part!r}") from None


def bom_cost(stuffing: Sequence[Decap]) -> float:
    """Sum of qty-1 unit prices, rounded to cents. Empty stuffing is $0.00."""
    return round(sum(unit_price_usd(cap) for cap in stuffing), 2)


def cost_within_budget(stuffing: Sequence[Decap], budget_usd: float) -> bool:
    """True when BOM cost is at or under ``budget_usd``."""
    return bom_cost(stuffing) <= budget_usd
