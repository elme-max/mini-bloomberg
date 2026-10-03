"""On-disk cache of fetched fundamentals.

Yahoo's unofficial API throttles clients that ask for the same data over and
over. Caching each company's snapshot for a few hours keeps repeat runs fast
and request-light, and lets recently fetched companies be re-scored offline.

Only live data is cached (never demo data). A missing, corrupt, expired or
schema-mismatched cache file is simply treated as a miss; a failure to write
the cache never breaks an analysis.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from .types import (
    FundamentalsSnapshot,
    QuarterFundamentals,
    ReportedMetrics,
    ValuationSnapshot,
)

CACHE_VERSION = 1
DEFAULT_TTL_HOURS = 12.0


def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "stock_evolution_model"


def snapshot_to_dict(snapshot: FundamentalsSnapshot) -> dict:
    return asdict(snapshot)


def snapshot_from_dict(data: dict) -> FundamentalsSnapshot:
    """Inverse of `snapshot_to_dict`; raises on any unexpected shape."""
    return FundamentalsSnapshot(
        symbol=data["symbol"],
        company_name=data["company_name"],
        is_demo_data=data["is_demo_data"],
        quarters=[QuarterFundamentals(**q) for q in data["quarters"]],
        valuation=ValuationSnapshot(**data["valuation"]),
        data_notes=list(data.get("data_notes", [])),
        annual=[QuarterFundamentals(**q) for q in data.get("annual", [])],
        sector=data.get("sector"),
        reported=ReportedMetrics(**data.get("reported", {})),
    )


def _describe_age(seconds: float) -> str:
    if seconds < 3600:
        return f"{seconds / 60:.0f} min ago"
    return f"{seconds / 3600:.1f} h ago"


class SnapshotCache:
    def __init__(
        self,
        directory: str | Path | None = None,
        ttl_hours: float = DEFAULT_TTL_HOURS,
        now: Callable[[], float] = time.time,
    ):
        self.directory = Path(directory) if directory else default_cache_dir()
        self.ttl_seconds = ttl_hours * 3600
        self._now = now
        self.hits = 0
        self.stores = 0

    def path_for(self, symbol: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", symbol.upper())
        return self.directory / f"{safe}.json"

    def get(self, symbol: str) -> FundamentalsSnapshot | None:
        symbol = symbol.upper()
        try:
            payload = json.loads(self.path_for(symbol).read_text())
            if payload["version"] != CACHE_VERSION or payload["symbol"] != symbol:
                return None
            fetched_at = payload["fetched_at"]
            age = self._now() - fetched_at
            if isinstance(fetched_at, bool) or not isinstance(fetched_at, (int, float)):
                return None
            if age < 0 or age > self.ttl_seconds:
                return None
            snapshot = snapshot_from_dict(payload["snapshot"])
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
        snapshot.data_notes = [*snapshot.data_notes, f"served from cache, fetched {_describe_age(age)}"]
        self.hits += 1
        return snapshot

    def put(self, symbol: str, snapshot: FundamentalsSnapshot) -> None:
        if snapshot.is_demo_data:
            return
        symbol = symbol.upper()
        payload = {
            "version": CACHE_VERSION,
            "symbol": symbol,
            "fetched_at": self._now(),
            "snapshot": snapshot_to_dict(snapshot),
        }
        path = self.path_for(symbol)
        temp = path.with_suffix(".tmp")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps(payload))
            os.replace(temp, path)  # atomic: readers never see a half-written file
        except OSError:
            return  # an unwritable cache must not break the analysis
        self.stores += 1
