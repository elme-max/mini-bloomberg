"""Sector-specific scoring bands.

A fixed set of thresholds treats every company alike: a bank's leverage or a
software firm's P/E would be judged against the same yardstick as an
industrial's. Each `SectorProfile` instead defines, per metric, the range that
maps onto a 0-100 score for that sector.

A band is `(zero_at, hundred_at)`: the metric value that scores 0 and the value
that scores 100, with a straight line in between. For "lower is better"
metrics (P/E, debt, ...) `zero_at` is therefore the larger number. A band of
`None` means the metric isn't meaningful for the sector (for example EBITDA
and current ratio for banks) and is skipped rather than scored.

IMPORTANT: these bands are hand-picked rules of thumb - roughly "weak" and
"strong" for a typical company in the sector - not statistically derived from
peer data. Treat them as a sensible starting point and tune them (ideally
against a backtest) before relying on them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

Band = tuple[float, float]


@dataclass(frozen=True)
class SectorProfile:
    name: str
    growth: Band | None = (-0.20, 0.30)  # revenue growth
    net_margin: Band | None = (-0.05, 0.25)
    roe: Band | None = (0.0, 0.30)
    peg: Band | None = (4.0, 0.5)
    trailing_pe: Band | None = (60.0, 8.0)
    forward_pe: Band | None = (50.0, 8.0)
    ev_to_ebitda: Band | None = (30.0, 6.0)
    price_to_sales: Band | None = (15.0, 1.0)
    price_to_book: Band | None = None  # only scored where it's the natural yardstick
    debt_to_equity: Band | None = (3.0, 0.0)
    current_ratio: Band | None = (0.5, 2.5)
    interest_coverage: Band | None = (1.5, 10.0)
    debt_to_ebitda: Band | None = (4.0, 0.0)
    fcf_margin: Band | None = (-0.10, 0.25)


# The original, sector-agnostic thresholds. Used when the sector is unknown.
GENERIC = SectorProfile(name="Generic")

_PROFILES: dict[str, SectorProfile] = {
    "Technology": replace(
        GENERIC,
        name="Technology",
        growth=(-0.05, 0.40),
        net_margin=(0.0, 0.30),
        roe=(0.05, 0.40),
        peg=(3.5, 0.8),
        trailing_pe=(70.0, 15.0),
        forward_pe=(55.0, 14.0),
        ev_to_ebitda=(40.0, 10.0),
        price_to_sales=(20.0, 3.0),
        debt_to_equity=(2.0, 0.0),
        current_ratio=(0.8, 3.0),
        interest_coverage=(3.0, 20.0),
        debt_to_ebitda=(3.0, 0.0),
        fcf_margin=(0.0, 0.30),
    ),
    "Communication Services": replace(
        GENERIC,
        name="Communication Services",
        growth=(-0.10, 0.25),
        net_margin=(0.0, 0.25),
        roe=(0.03, 0.30),
        peg=(3.5, 0.8),
        trailing_pe=(50.0, 10.0),
        forward_pe=(40.0, 10.0),
        ev_to_ebitda=(20.0, 6.0),
        price_to_sales=(8.0, 1.5),
        debt_to_equity=(3.0, 0.3),
        current_ratio=(0.5, 2.0),
        interest_coverage=(2.0, 12.0),
        debt_to_ebitda=(5.0, 0.5),
        fcf_margin=(0.0, 0.25),
    ),
    "Healthcare": replace(
        GENERIC,
        name="Healthcare",
        growth=(-0.05, 0.25),
        peg=(3.5, 0.8),
        trailing_pe=(60.0, 12.0),
        forward_pe=(40.0, 10.0),
        ev_to_ebitda=(30.0, 8.0),
        price_to_sales=(10.0, 1.5),
        debt_to_equity=(2.5, 0.0),
        current_ratio=(0.8, 3.0),
        interest_coverage=(2.0, 12.0),
        fcf_margin=(-0.05, 0.25),
    ),
    "Financial Services": replace(
        GENERIC,
        name="Financial Services",
        growth=(-0.10, 0.20),
        net_margin=(0.05, 0.35),
        roe=(0.04, 0.18),
        peg=(3.0, 0.7),
        trailing_pe=(25.0, 7.0),
        forward_pe=(20.0, 7.0),
        ev_to_ebitda=None,  # interest is an operating cost; EBITDA isn't meaningful
        price_to_sales=(6.0, 1.5),
        price_to_book=(3.0, 0.8),
        debt_to_equity=(8.0, 1.0),  # leverage is the business model
        current_ratio=None,  # no current/non-current balance sheet split
        interest_coverage=None,
        debt_to_ebitda=None,
        fcf_margin=None,  # operating cash flow is dominated by deposits and loans
    ),
    "Consumer Cyclical": replace(
        GENERIC,
        name="Consumer Cyclical",
        growth=(-0.15, 0.20),
        net_margin=(-0.03, 0.12),
        peg=(3.5, 0.8),
        trailing_pe=(45.0, 9.0),
        forward_pe=(35.0, 9.0),
        ev_to_ebitda=(20.0, 6.0),
        price_to_sales=(3.0, 0.3),
        debt_to_equity=(3.0, 0.2),
        current_ratio=(0.7, 2.0),
        debt_to_ebitda=(4.5, 0.5),
        fcf_margin=(-0.05, 0.12),
    ),
    "Consumer Defensive": replace(
        GENERIC,
        name="Consumer Defensive",
        growth=(-0.05, 0.10),
        net_margin=(0.0, 0.12),
        roe=(0.05, 0.30),
        peg=(4.0, 1.0),
        trailing_pe=(35.0, 12.0),
        forward_pe=(30.0, 12.0),
        ev_to_ebitda=(18.0, 8.0),
        price_to_sales=(3.0, 0.4),
        debt_to_equity=(2.5, 0.3),
        current_ratio=(0.6, 1.8),
        interest_coverage=(3.0, 12.0),
        debt_to_ebitda=(4.0, 0.5),
        fcf_margin=(0.0, 0.12),
    ),
    "Industrials": replace(
        GENERIC,
        name="Industrials",
        growth=(-0.10, 0.15),
        net_margin=(0.0, 0.15),
        roe=(0.03, 0.30),
        peg=(3.5, 1.0),
        trailing_pe=(40.0, 10.0),
        forward_pe=(30.0, 10.0),
        ev_to_ebitda=(20.0, 7.0),
        price_to_sales=(4.0, 0.6),
        debt_to_equity=(2.5, 0.2),
        current_ratio=(0.8, 2.2),
        interest_coverage=(2.0, 12.0),
        debt_to_ebitda=(4.0, 0.5),
        fcf_margin=(0.0, 0.12),
    ),
    "Energy": replace(
        GENERIC,
        name="Energy",
        growth=(-0.30, 0.30),  # commodity-price cycles swing revenue widely
        net_margin=(-0.05, 0.15),
        roe=(0.0, 0.25),
        peg=(4.0, 0.8),
        trailing_pe=(30.0, 5.0),
        forward_pe=(25.0, 5.0),
        ev_to_ebitda=(12.0, 3.0),
        price_to_sales=(3.0, 0.4),
        debt_to_equity=(2.0, 0.0),
        current_ratio=(0.7, 2.0),
        interest_coverage=(2.0, 15.0),
        debt_to_ebitda=(3.5, 0.3),
        fcf_margin=(-0.05, 0.20),
    ),
    "Utilities": replace(
        GENERIC,
        name="Utilities",
        growth=(-0.05, 0.10),
        net_margin=(0.02, 0.18),
        roe=(0.02, 0.12),
        peg=(4.0, 1.0),
        trailing_pe=(30.0, 11.0),
        forward_pe=(25.0, 11.0),
        ev_to_ebitda=(18.0, 8.0),
        price_to_sales=(4.0, 1.0),
        debt_to_equity=(4.0, 0.8),  # regulated, capital-intensive: debt is normal
        current_ratio=(0.4, 1.2),
        interest_coverage=(1.5, 6.0),
        debt_to_ebitda=(8.0, 3.0),
        fcf_margin=(-0.20, 0.10),  # heavy ongoing capex
    ),
    "Real Estate": replace(
        GENERIC,
        name="Real Estate",
        growth=(-0.05, 0.15),
        net_margin=(0.0, 0.35),  # depreciation depresses reported earnings
        roe=(0.0, 0.12),
        peg=None,  # earnings growth isn't how REITs are valued
        trailing_pe=(60.0, 15.0),
        forward_pe=(50.0, 15.0),
        ev_to_ebitda=(30.0, 12.0),
        price_to_sales=(15.0, 4.0),
        debt_to_equity=(4.0, 0.5),
        current_ratio=None,  # no current/non-current balance sheet split
        interest_coverage=(1.5, 6.0),
        debt_to_ebitda=(9.0, 4.0),
        fcf_margin=(0.0, 0.40),
    ),
    "Basic Materials": replace(
        GENERIC,
        name="Basic Materials",
        growth=(-0.20, 0.20),
        net_margin=(-0.03, 0.18),
        roe=(0.0, 0.25),
        peg=(4.0, 0.8),
        trailing_pe=(35.0, 6.0),
        forward_pe=(30.0, 6.0),
        ev_to_ebitda=(14.0, 4.0),
        price_to_sales=(4.0, 0.6),
        debt_to_equity=(2.0, 0.0),
        current_ratio=(0.8, 2.5),
        interest_coverage=(2.0, 12.0),
        debt_to_ebitda=(4.0, 0.3),
        fcf_margin=(-0.05, 0.15),
    ),
}

# Yahoo Finance uses its own sector names; also accept GICS-style names.
_ALIASES = {
    "information technology": "Technology",
    "tech": "Technology",
    "telecommunication services": "Communication Services",
    "health care": "Healthcare",
    "financials": "Financial Services",
    "financial": "Financial Services",
    "consumer discretionary": "Consumer Cyclical",
    "consumer staples": "Consumer Defensive",
    "materials": "Basic Materials",
}

_BY_KEY = {name.lower(): profile for name, profile in _PROFILES.items()}


def profile_for(sector: str | None) -> SectorProfile:
    """Scoring profile for a sector name; the generic profile if unknown."""
    if not sector:
        return GENERIC
    key = sector.strip().lower()
    key = _ALIASES.get(key, key).lower()
    return _BY_KEY.get(key, GENERIC)


def available_sectors() -> list[str]:
    return sorted(_PROFILES)
