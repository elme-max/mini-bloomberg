"""Backtest the model's scores against what the stocks did next.

Question answered: do high-scoring companies actually go on to beat
low-scoring ones, which of the five categories carry that signal, and would
different category weights have done better?

How it stays honest
-------------------
* Point-in-time: at each as-of date a company is scored using only quarters
  that had already been *reported* (period end + a reporting lag), and
  valuation multiples are rebuilt from the price on that date. Yahoo's
  "current" figures are never used here - they would leak the future.
* Forward return is measured over a window that starts after the as-of date.
* Weights are fitted on the earlier dates only and judged on later, unseen
  dates (chronological split, no shuffling), with shrinkage toward equal
  weights. Fitted weights are only recommended if they win out-of-sample.
* Band thresholds are *diagnosed* (how often a category saturates at 0 or
  100), not auto-tuned - tuning dozens of cut-offs on a small sample would
  just overfit.

Data: two CSV files (see README). `export` can pull them from Yahoo, but Yahoo
only serves ~4-5 recent quarters, which is far too little for a meaningful
backtest; use a deeper source for real conclusions.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable, Iterator

from .model import DEFAULT_WEIGHTS, StockEvolutionModel
from .types import FundamentalsSnapshot, QuarterFundamentals, ValuationSnapshot

CATEGORIES = list(DEFAULT_WEIGHTS)
NUMERIC_COLUMNS = [
    "revenue", "gross_profit", "operating_income", "net_income", "total_assets",
    "total_equity", "total_debt", "current_assets", "current_liabilities",
    "interest_expense", "ebitda", "operating_cash_flow", "capex",
]
PRICE_STALENESS_DAYS = 10  # a price older than this is treated as missing
MIN_QUARTERS = 4  # trailing-12-month figures need a full year visible
MIN_DATES_TO_JUDGE = 4  # per side of the train/test split


# --------------------------------------------------------------------------- data


@dataclass
class FundamentalRow:
    period_end: date
    quarter: QuarterFundamentals
    shares: float | None


PriceSeries = tuple[list[date], list[float]]  # sorted dates, matching closes


def _finite(raw: str, where: str) -> float:
    try:
        value = float((raw or "").strip())
    except ValueError:
        raise ValueError(f"{where} must be a number, got {raw!r}") from None
    if not math.isfinite(value):
        raise ValueError(f"{where} must be a finite number, got {raw!r}")
    return value


def load_fundamentals(path: str | Path) -> tuple[dict[str, list[FundamentalRow]], dict[str, str]]:
    """Read the fundamentals CSV -> ({symbol: rows oldest-first}, {symbol: sector}).

    Required columns: symbol, period_end (YYYY-MM-DD) and every column in
    NUMERIC_COLUMNS. Optional: shares_outstanding, sector. Blank or non-numeric
    required values are an error rather than a silent zero.
    """

    rows: dict[str, list[FundamentalRow]] = {}
    sectors: dict[str, str] = {}
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in ("symbol", "period_end", *NUMERIC_COLUMNS) if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing column(s): {', '.join(missing)}")
        for line_no, record in enumerate(reader, start=2):
            where = f"{path} line {line_no}"
            symbol = (record["symbol"] or "").strip().upper()
            if not symbol:
                raise ValueError(f"{where}: empty symbol")
            try:
                period_end = date.fromisoformat((record["period_end"] or "").strip())
            except ValueError:
                raise ValueError(f"{where}: period_end must be YYYY-MM-DD, got {record['period_end']!r}") from None
            values = {col: _finite(record[col], f"{where}: {col}") for col in NUMERIC_COLUMNS}
            shares_raw = (record.get("shares_outstanding") or "").strip()
            shares = _finite(shares_raw, f"{where}: shares_outstanding") if shares_raw else None
            rows.setdefault(symbol, []).append(
                FundamentalRow(period_end, QuarterFundamentals(period=period_end.isoformat(), **values), shares)
            )
            sector = (record.get("sector") or "").strip()
            if sector:
                sectors.setdefault(symbol, sector)
    for symbol_rows in rows.values():
        symbol_rows.sort(key=lambda r: r.period_end)
    return rows, sectors


def load_prices(path: str | Path) -> dict[str, PriceSeries]:
    """Read the prices CSV (symbol, date, close) -> {symbol: (dates, closes)}."""

    raw: dict[str, list[tuple[date, float]]] = {}
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in ("symbol", "date", "close") if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing column(s): {', '.join(missing)}")
        for line_no, record in enumerate(reader, start=2):
            where = f"{path} line {line_no}"
            try:
                day = date.fromisoformat((record["date"] or "").strip())
            except ValueError:
                raise ValueError(f"{where}: date must be YYYY-MM-DD, got {record['date']!r}") from None
            close = _finite(record["close"], f"{where}: close")
            if close <= 0:
                raise ValueError(f"{where}: close must be positive, got {close}")
            raw.setdefault((record["symbol"] or "").strip().upper(), []).append((day, close))
    series: dict[str, PriceSeries] = {}
    for symbol, points in raw.items():
        points.sort()
        series[symbol] = ([d for d, _ in points], [c for _, c in points])
    return series


def price_at(series: PriceSeries, day: date, max_stale: int = PRICE_STALENESS_DAYS) -> float | None:
    """Last close on or before `day`, or None if it is older than `max_stale` days."""
    dates, closes = series
    index = bisect.bisect_right(dates, day) - 1
    if index < 0 or (day - dates[index]).days > max_stale:
        return None
    return closes[index]


def forward_return(series: PriceSeries, as_of: date, horizon_days: int) -> float | None:
    start = price_at(series, as_of)
    end = price_at(series, as_of + timedelta(days=horizon_days))
    if start is None or end is None:
        return None
    return end / start - 1


# ------------------------------------------------------------------ point-in-time


def _valuation_as_of(quarters: list[QuarterFundamentals], shares: float | None, price: float | None) -> ValuationSnapshot:
    """Multiples rebuilt from the as-of price. PEG, forward P/E and EV/EBITDA are
    left out: they need analyst estimates or cash balances this data lacks."""

    if price is None or not shares or shares <= 0:
        return ValuationSnapshot(share_price=price)
    window = quarters[-4:]
    revenue = sum(q.revenue for q in window)
    net_income = sum(q.net_income for q in window)
    market_cap = price * shares
    equity = window[-1].total_equity
    return ValuationSnapshot(
        share_price=price,
        market_cap=market_cap,
        trailing_pe=market_cap / net_income if net_income > 0 else None,
        price_to_sales=market_cap / revenue if revenue > 0 else None,
        price_to_book=market_cap / equity if equity > 0 else None,
    )


def snapshot_as_of(
    symbol: str,
    rows: list[FundamentalRow],
    series: PriceSeries | None,
    as_of: date,
    lag_days: int,
    sector: str | None = None,
    min_quarters: int = MIN_QUARTERS,
) -> FundamentalsSnapshot | None:
    """What an investor could have known on `as_of`: quarters reported by then only."""

    visible = [r for r in rows if r.period_end + timedelta(days=lag_days) <= as_of][-8:]
    if len(visible) < min_quarters:
        return None
    quarters = [r.quarter for r in visible]
    price = price_at(series, as_of) if series else None
    return FundamentalsSnapshot(
        symbol=symbol,
        company_name=symbol,
        is_demo_data=False,
        quarters=quarters,
        valuation=_valuation_as_of(quarters, visible[-1].shares, price),
        data_notes=["point-in-time reconstruction"],
        sector=sector,
    )  # `reported` stays empty on purpose: Yahoo's current figures would leak the future


@dataclass
class Observation:
    symbol: str
    as_of: date
    scores: dict[str, float]  # category name -> 0-100 score at as_of
    forward_return: float


def rebalance_dates(
    fundamentals: dict[str, list[FundamentalRow]],
    prices: dict[str, PriceSeries],
    horizon_days: int,
    lag_days: int,
    step_days: int | None = None,
) -> list[date]:
    """Evenly spaced as-of dates. Spacing >= horizon keeps the forward windows
    from overlapping, so each date is an independent observation."""

    step = step_days or horizon_days
    starts = [rows[MIN_QUARTERS - 1].period_end + timedelta(days=lag_days)
              for rows in fundamentals.values() if len(rows) >= MIN_QUARTERS]
    if not starts or not prices:
        return []
    last = max(dates[-1] for dates, _ in prices.values()) - timedelta(days=horizon_days)
    dates = []
    current = min(starts)
    while current <= last:
        dates.append(current)
        current += timedelta(days=step)
    return dates


def build_observations(
    fundamentals: dict[str, list[FundamentalRow]],
    prices: dict[str, PriceSeries],
    sectors: dict[str, str] | None = None,
    horizon_days: int = 90,
    lag_days: int = 45,
    step_days: int | None = None,
    as_of_dates: Iterable[date] | None = None,
    model: StockEvolutionModel | None = None,
) -> list[Observation]:
    model = model or StockEvolutionModel()
    sectors = sectors or {}
    dates = list(as_of_dates) if as_of_dates is not None else rebalance_dates(
        fundamentals, prices, horizon_days, lag_days, step_days
    )
    observations: list[Observation] = []
    for as_of in dates:
        for symbol, rows in fundamentals.items():
            series = prices.get(symbol)
            if not series:
                continue
            outcome = forward_return(series, as_of, horizon_days)
            snapshot = snapshot_as_of(symbol, rows, series, as_of, lag_days, sectors.get(symbol))
            if outcome is None or snapshot is None:
                continue
            report = model.analyze_snapshot(snapshot)
            observations.append(
                Observation(symbol, as_of, {c.name: c.score for c in report.categories}, outcome)
            )
    return observations


# ------------------------------------------------------------------------ statistics


def _ranks(values: list[float]) -> list[float]:
    """1-based ranks, ties share their average rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    mean_a, mean_b = sum(a) / n, sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    if var_a == 0 or var_b == 0:
        return None
    return cov / math.sqrt(var_a * var_b)


def spearman(x: list[float], y: list[float]) -> float | None:
    """Rank correlation; None when undefined (fewer than 3 points or no variation)."""
    if len(x) != len(y) or len(x) < 3:
        return None
    return _pearson(_ranks(x), _ranks(y))


def top_minus_bottom(scores: list[float], returns: list[float], fraction: float = 0.2) -> float:
    """Average return of the best-scored `fraction` minus the worst-scored `fraction`."""
    order = sorted(range(len(scores)), key=lambda i: (scores[i], i))
    k = max(1, round(len(scores) * fraction))
    bottom = [returns[i] for i in order[:k]]
    top = [returns[i] for i in order[-k:]]
    return sum(top) / len(top) - sum(bottom) / len(bottom)


@dataclass
class ICStats:
    """Signal quality of one score: rank information coefficient (IC) by date."""

    mean_ic: float | None
    t_stat: float | None
    n_dates: int
    mean_spread: float | None  # top fifth minus bottom fifth, average forward return
    avg_names: float = 0.0
    clipped_share: float | None = None  # share of scores stuck at 0 or 100


def _summarize(ics: list[float], spreads: list[float], avg_names: float) -> ICStats:
    if not ics:
        return ICStats(None, None, 0, None, avg_names)
    mean_ic = sum(ics) / len(ics)
    t_stat = None
    if len(ics) >= 3:
        variance = sum((v - mean_ic) ** 2 for v in ics) / (len(ics) - 1)
        if variance > 0:
            t_stat = mean_ic / math.sqrt(variance / len(ics))
    return ICStats(mean_ic, t_stat, len(ics), sum(spreads) / len(spreads), avg_names)


def group_by_date(observations: Iterable[Observation]) -> dict[date, list[Observation]]:
    grouped: dict[date, list[Observation]] = {}
    for obs in observations:
        grouped.setdefault(obs.as_of, []).append(obs)
    return grouped


def _ic_stats(
    observations: list[Observation],
    scorer: Callable[[Observation], float],
    min_names: int,
    fraction: float = 0.2,
) -> ICStats:
    ics, spreads, sizes = [], [], []
    for _, group in sorted(group_by_date(observations).items()):
        if len(group) < min_names:
            continue
        scores = [scorer(o) for o in group]
        returns = [o.forward_return for o in group]
        ic = spearman(scores, returns)
        if ic is None:
            continue
        ics.append(ic)
        spreads.append(top_minus_bottom(scores, returns, fraction))
        sizes.append(len(group))
    return _summarize(ics, spreads, sum(sizes) / len(sizes) if sizes else 0.0)


def _normalized(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.get(c, 0.0) for c in CATEGORIES)
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    return {c: weights.get(c, 0.0) / total for c in CATEGORIES}


def evaluate_weights(observations: list[Observation], weights: dict[str, float], min_names: int = 5) -> ICStats:
    w = _normalized(weights)
    return _ic_stats(observations, lambda o: sum(w[c] * o.scores[c] for c in CATEGORIES), min_names)


def evaluate(observations: list[Observation], min_names: int = 5) -> dict[str, ICStats]:
    """Signal quality per category plus the equal-weighted overall score."""

    stats: dict[str, ICStats] = {}
    for category in CATEGORIES:
        result = _ic_stats(observations, lambda o, c=category: o.scores[c], min_names)
        scores = [o.scores[category] for o in observations]
        if scores:
            result.clipped_share = sum(1 for s in scores if s <= 0.5 or s >= 99.5) / len(scores)
        stats[category] = result
    stats["Overall (equal weights)"] = evaluate_weights(observations, DEFAULT_WEIGHTS, min_names)
    return stats


# ---------------------------------------------------------------------- weight fitting


def _weight_grid(parts: int, steps: int) -> Iterator[list[float]]:
    def compositions(remaining: int, slots: int) -> Iterator[tuple[int, ...]]:
        if slots == 1:
            yield (remaining,)
            return
        for first in range(remaining + 1):
            for rest in compositions(remaining - first, slots - 1):
                yield (first, *rest)

    for combo in compositions(steps, parts):
        yield [c / steps for c in combo]


def fit_weights(
    observations: list[Observation],
    min_names: int = 5,
    steps: int = 10,
    shrink: float = 0.5,
) -> dict[str, float]:
    """Category weights that maximize the average rank IC on `observations`.

    Searches every weight combination on a grid (steps=10 -> multiples of 0.10),
    then shrinks the winner `shrink` of the way back toward equal weights, since
    a fit on limited history is optimistic. Ties go to the most balanced weights.
    """

    prepared = []
    for _, group in sorted(group_by_date(observations).items()):
        if len(group) < min_names:
            continue
        returns = _ranks([o.forward_return for o in group])
        prepared.append(([[o.scores[c] for c in CATEGORIES] for o in group], returns))

    equal = [1 / len(CATEGORIES)] * len(CATEGORIES)
    best, best_key = equal, None
    for candidate in _weight_grid(len(CATEGORIES), steps):
        ics = []
        for rows, return_ranks in prepared:
            combined = [sum(w * s for w, s in zip(candidate, row)) for row in rows]
            ic = _pearson(_ranks(combined), return_ranks)
            if ic is not None:
                ics.append(ic)
        if not ics:
            continue
        distance = sum((w - e) ** 2 for w, e in zip(candidate, equal))
        key = (round(sum(ics) / len(ics), 12), -distance)
        if best_key is None or key > best_key:
            best, best_key = candidate, key

    blended = [(1 - shrink) * b + shrink * e for b, e in zip(best, equal)]
    return dict(zip(CATEGORIES, blended))


@dataclass
class WalkForward:
    n_train_dates: int
    n_test_dates: int
    fitted_weights: dict[str, float]
    equal_train: ICStats
    fitted_train: ICStats
    equal_test: ICStats
    fitted_test: ICStats
    adopt: bool
    verdict: str
    train_end: date | None = None  # last date used for fitting
    test_start: date | None = None  # first date used for judging (always later)


def _verdict(n_train: int, n_test: int, equal_test: ICStats, fitted_test: ICStats) -> tuple[bool, str]:
    if n_train < MIN_DATES_TO_JUDGE or n_test < MIN_DATES_TO_JUDGE:
        return False, (
            f"Too few dates to judge (need at least {MIN_DATES_TO_JUDGE} train and "
            f"{MIN_DATES_TO_JUDGE} test, got {n_train} and {n_test}). Keep the default weights."
        )
    if equal_test.mean_ic is None or fitted_test.mean_ic is None:
        return False, "Out-of-sample IC could not be computed. Keep the default weights."
    if fitted_test.mean_ic > equal_test.mean_ic + 0.01 and fitted_test.mean_ic > 0:
        return True, ("Fitted weights beat equal weights on dates they were not fitted on "
                      "and the signal is positive: reasonable to adopt (re-check as data grows).")
    return False, ("Fitted weights did NOT beat equal weights out-of-sample, so any in-sample "
                   "edge was probably overfit. Keep the default weights.")


def walk_forward(
    observations: list[Observation],
    train_fraction: float = 0.6,
    min_names: int = 5,
    steps: int = 10,
    shrink: float = 0.5,
) -> WalkForward:
    """Fit on the earliest dates, judge on the later ones (never the reverse)."""

    dates = sorted(group_by_date(observations))
    n_train = min(max(1, int(len(dates) * train_fraction)), max(len(dates) - 1, 0))
    train_dates, test_dates = set(dates[:n_train]), set(dates[n_train:])
    train = [o for o in observations if o.as_of in train_dates]
    test = [o for o in observations if o.as_of in test_dates]

    fitted = fit_weights(train, min_names, steps, shrink)
    equal_test = evaluate_weights(test, DEFAULT_WEIGHTS, min_names)
    fitted_test = evaluate_weights(test, fitted, min_names)
    adopt, verdict = _verdict(len(train_dates), len(test_dates), equal_test, fitted_test)
    return WalkForward(
        n_train_dates=len(train_dates),
        n_test_dates=len(test_dates),
        fitted_weights=fitted,
        equal_train=evaluate_weights(train, DEFAULT_WEIGHTS, min_names),
        fitted_train=evaluate_weights(train, fitted, min_names),
        equal_test=equal_test,
        fitted_test=fitted_test,
        adopt=adopt,
        verdict=verdict,
        train_end=dates[n_train - 1] if n_train else None,
        test_start=dates[n_train] if n_train < len(dates) else None,
    )


# ------------------------------------------------------------------------------ run


@dataclass
class BacktestResult:
    horizon_days: int
    lag_days: int
    n_observations: int
    first_date: date | None
    last_date: date | None
    stats: dict[str, ICStats]
    walk_forward: WalkForward | None
    warnings: list[str] = field(default_factory=list)


def run_backtest(
    fundamentals_path: str | Path,
    prices_path: str | Path,
    horizon_days: int = 90,
    lag_days: int = 45,
    min_names: int = 5,
    train_fraction: float = 0.6,
    steps: int = 10,
    shrink: float = 0.5,
) -> BacktestResult:
    fundamentals, sectors = load_fundamentals(fundamentals_path)
    prices = load_prices(prices_path)
    observations = build_observations(fundamentals, prices, sectors, horizon_days, lag_days)
    dates = sorted(group_by_date(observations))

    warnings: list[str] = []
    stats = evaluate(observations, min_names) if observations else {}
    overall = stats.get("Overall (equal weights)")
    n_dates = overall.n_dates if overall else 0
    if observations and n_dates == 0:
        # e.g. a one-company export: scored, but nothing to rank against
        return BacktestResult(
            horizon_days=horizon_days, lag_days=lag_days, n_observations=len(observations),
            first_date=dates[0], last_date=dates[-1], stats={}, walk_forward=None,
            warnings=[f"{len(observations)} observation(s), but no as-of date had at least {min_names} "
                      "companies with a usable score, so no statistics could be computed. "
                      "Use more companies (30+ recommended) or lower --min-names."],
        )
    if observations and n_dates < 8:
        warnings.append(f"Only {n_dates} usable rebalance date(s): IC estimates are very noisy "
                        "(aim for 12+ dates of 30+ companies).")
    if overall and 0 < overall.avg_names < 20:
        warnings.append(f"Only {overall.avg_names:.0f} companies per date on average: "
                        "rankings are unreliable (aim for 30+).")
    for name, s in stats.items():
        if s.clipped_share is not None and s.clipped_share > 0.25:
            warnings.append(f"{name}: {s.clipped_share * 100:.2f}% of scores sit at exactly 0 or 100 - "
                            "its sector bands may be too narrow to separate companies.")
    return BacktestResult(
        horizon_days=horizon_days,
        lag_days=lag_days,
        n_observations=len(observations),
        first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
        stats=stats,
        walk_forward=walk_forward(observations, train_fraction, min_names, steps, shrink) if observations else None,
        warnings=warnings,
    )


def _fmt(value: float | None, pattern: str = "{:+.2f}") -> str:
    return "n/a" if value is None else pattern.format(value)


def format_backtest(result: BacktestResult) -> str:
    if not result.n_observations:
        return ("No usable observations. Each company needs at least "
                f"{MIN_QUARTERS} reported quarters visible at an as-of date AND prices covering the "
                f"{result.horizon_days}-day window after it.\n")
    if not result.stats:
        return "No statistics computed.\n" + "".join(f"  - {w}\n" for w in result.warnings)
    lines = [
        f"BACKTEST - {result.n_observations} observations, as-of dates {result.first_date} to "
        f"{result.last_date}, forward window {result.horizon_days} days, reporting lag {result.lag_days} days",
        "",
        "Signal quality. Mean IC = rank correlation between score and forward return (above 0 is good);",
        "Top-Bottom = average return of the best-scored fifth minus the worst-scored fifth;",
        "Clipped = share of scores stuck at 0 or 100.",
        f"  {'Score':<26}{'Mean IC':>9}{'t-stat':>9}{'Top-Bottom':>13}{'Clipped':>10}{'Dates':>7}",
    ]
    for name, s in result.stats.items():
        lines.append(
            f"  {name:<26}{_fmt(s.mean_ic):>9}{_fmt(s.t_stat):>9}"
            f"{_fmt(s.mean_spread and s.mean_spread * 100, '{:+.2f}%'):>13}"
            f"{_fmt(s.clipped_share and s.clipped_share * 100, '{:.2f}%') if s.clipped_share is not None else '-':>10}"
            f"{s.n_dates:>7}"
        )
    wf = result.walk_forward
    if wf:
        lines += ["", f"Weight fitting - fitted on the first {wf.n_train_dates} dates (to {wf.train_end}), "
                      f"judged on the later {wf.n_test_dates} (from {wf.test_start}); never the reverse. "
                      "Winner shrunk toward equal weights:"]
        lines.append("  Fitted weights: " + ", ".join(f"{c} {w:.2f}" for c, w in wf.fitted_weights.items()))
        lines.append(f"  {'':<16}{'in-sample IC':>14}{'out-of-sample IC':>19}")
        lines.append(f"  {'Equal weights':<16}{_fmt(wf.equal_train.mean_ic):>14}{_fmt(wf.equal_test.mean_ic):>19}")
        lines.append(f"  {'Fitted weights':<16}{_fmt(wf.fitted_train.mean_ic):>14}{_fmt(wf.fitted_test.mean_ic):>19}")
        lines += ["", "Verdict: " + wf.verdict]
        if wf.adopt:
            weights = ", ".join(f'"{c}": {w:.2f}' for c, w in wf.fitted_weights.items())
            lines.append(f"  StockEvolutionModel(weights={{{weights}}})")
    if result.warnings:
        lines += ["", "Warnings:"] + [f"  - {w}" for w in result.warnings]
    return "\n".join(lines) + "\n"


def result_to_dict(result: BacktestResult) -> dict:
    def stats(s: ICStats) -> dict:
        return {
            "mean_ic": None if s.mean_ic is None else round(s.mean_ic, 2),
            "t_stat": None if s.t_stat is None else round(s.t_stat, 2),
            "n_dates": s.n_dates,
            "top_minus_bottom": None if s.mean_spread is None else round(s.mean_spread, 4),
            "clipped_share": None if s.clipped_share is None else round(s.clipped_share, 4),
        }

    wf = result.walk_forward
    return {
        "horizon_days": result.horizon_days,
        "lag_days": result.lag_days,
        "observations": result.n_observations,
        "first_date": str(result.first_date) if result.first_date else None,
        "last_date": str(result.last_date) if result.last_date else None,
        "stats": {name: stats(s) for name, s in result.stats.items()},
        "walk_forward": None if wf is None else {
            "train_dates": wf.n_train_dates,
            "test_dates": wf.n_test_dates,
            "fitted_weights": {c: round(w, 2) for c, w in wf.fitted_weights.items()},
            "equal_train": stats(wf.equal_train), "fitted_train": stats(wf.fitted_train),
            "equal_test": stats(wf.equal_test), "fitted_test": stats(wf.fitted_test),
            "adopt": wf.adopt, "verdict": wf.verdict,
        },
        "warnings": result.warnings,
    }


# ------------------------------------------------------------------- Yahoo export


@dataclass
class ExportSummary:
    exported: dict[str, int] = field(default_factory=dict)  # symbol -> quarters written
    errors: dict[str, str] = field(default_factory=dict)


def export_yahoo_history(symbols: Iterable[str], out_dir: str | Path) -> ExportSummary:
    """Write fundamentals.csv and prices.csv for `symbols` from Yahoo Finance.

    Yahoo serves only ~4-5 recent quarters, and shares outstanding is today's
    figure applied to every quarter, so this is enough to try the pipeline but
    NOT enough for conclusions. Prices are split/dividend adjusted.
    """

    from . import fetch as fetch_module  # looked up at call time (patchable in tests)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = ExportSummary()
    fundamentals_rows: list[dict] = []
    price_rows: list[dict] = []

    for raw_symbol in symbols:
        symbol = raw_symbol.upper()
        try:
            snapshot = fetch_module.fetch_fundamentals(symbol)
            ticker = fetch_module.yf.Ticker(symbol)
            try:
                shares = (ticker.get_info() or {}).get("sharesOutstanding")
            except Exception:  # noqa: BLE001 - valuation is optional
                shares = None
            history = ticker.history(period="max", auto_adjust=True)
            closes = [(ts.date(), float(v)) for ts, v in history["Close"].items() if v == v and v > 0]
            if not closes:
                raise ValueError("no price history")
            quarter_rows = []
            for q in snapshot.quarters:
                date.fromisoformat(q.period)  # must be a real quarter-end date
                quarter_rows.append({
                    "symbol": symbol, "sector": snapshot.sector or "", "period_end": q.period,
                    **{col: getattr(q, col) for col in NUMERIC_COLUMNS},
                    "shares_outstanding": shares if isinstance(shares, (int, float)) else "",
                })
        except Exception as exc:  # noqa: BLE001 - report per symbol, keep going
            summary.errors[symbol] = str(exc)
            continue
        fundamentals_rows.extend(quarter_rows)
        price_rows.extend({"symbol": symbol, "date": d.isoformat(), "close": c} for d, c in closes)
        summary.exported[symbol] = len(quarter_rows)

    fundamentals_columns = ["symbol", "sector", "period_end", *NUMERIC_COLUMNS, "shares_outstanding"]
    with open(out / "fundamentals.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fundamentals_columns)
        writer.writeheader()
        writer.writerows(fundamentals_rows)
    with open(out / "prices.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "close"])
        writer.writeheader()
        writer.writerows(price_rows)
    return summary


# ------------------------------------------------------------------------------ CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock_evolution_model.backtest",
        description="Test the model's scores and category weights against forward stock returns.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Backtest from a fundamentals CSV and a prices CSV")
    run.add_argument("--fundamentals", required=True, help="fundamentals CSV (see README for columns)")
    run.add_argument("--prices", required=True, help="prices CSV: symbol,date,close")
    run.add_argument("--horizon", type=int, default=90, help="forward-return window in days (default 90)")
    run.add_argument("--lag", type=int, default=45, help="days after quarter end before its numbers count as known (default 45)")
    run.add_argument("--min-names", type=int, default=5, help="minimum companies for a date to count (default 5)")
    run.add_argument("--train-fraction", type=float, default=0.6, help="share of earliest dates used for fitting (default 0.6)")
    run.add_argument("--shrink", type=float, default=0.5, help="how far to pull fitted weights back toward equal, 0-1 (default 0.5)")
    run.add_argument("--json", action="store_true", help="machine-readable output")

    export = sub.add_parser("export", help="Write the two CSVs from Yahoo Finance (limited history)")
    export.add_argument("tickers", nargs="+")
    export.add_argument("--out", default="history", help="output directory (default ./history)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "export":
        summary = export_yahoo_history(args.tickers, args.out)
        for symbol, quarters in summary.exported.items():
            print(f"{symbol}: {quarters} quarters written")
        for symbol, message in summary.errors.items():
            print(f"{symbol}: ERROR - {message}", file=sys.stderr)
        if summary.exported:
            print(f"\nWrote {args.out}/fundamentals.csv and {args.out}/prices.csv.\n"
                  "NOTE: Yahoo provides only ~4-5 recent quarters, so a backtest on this data will have "
                  "almost no usable dates. It is enough to try the pipeline; use a deeper historical "
                  "source for real conclusions.")
        return 0 if summary.exported and not summary.errors else 1

    try:
        result = run_backtest(args.fundamentals, args.prices, args.horizon, args.lag,
                              args.min_names, args.train_fraction, shrink=args.shrink)
    except (OSError, ValueError) as exc:
        print(f"ERROR - {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result_to_dict(result), indent=2) if args.json else format_backtest(result), end="")
    return 0 if result.stats else 1


if __name__ == "__main__":
    sys.exit(main())
