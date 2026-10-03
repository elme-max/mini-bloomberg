"""Top-level orchestration: fetch -> derive metrics -> score -> report."""

from __future__ import annotations

from dataclasses import replace

from . import scoring
from .fetch import fetch_fundamentals
from .metrics import best_revenue_growth, compute_quarter_metrics, compute_ttm
from .sectors import GENERIC, profile_for
from .types import (
    CategoryResult,
    EvolutionReport,
    FundamentalsSnapshot,
    ReportedMetrics,
    SourceComparison,
)

DEFAULT_WEIGHTS = {
    "Revenue Growth": 0.20,
    "Profitability": 0.20,
    "Valuation": 0.20,
    "Debt Levels": 0.20,
    "Cash Flow Trends": 0.20,
}


class StockEvolutionModel:
    """AI-powered multi-factor model for evaluating a company's fundamental trajectory.

    Scores five categories - revenue growth, profitability, valuation,
    debt levels, and cash flow trends - each 0-100, from up to eight
    quarters of fundamentals, then combines them into a weighted overall
    score, letter grade, and trend direction.
    """

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = dict(weights) if weights else dict(DEFAULT_WEIGHTS)
        total = sum(self.weights.values())
        if total <= 0:
            raise ValueError("weights must sum to a positive number")
        self.weights = {k: v / total for k, v in self.weights.items()}

    def analyze(self, symbol: str, demo: bool = False) -> EvolutionReport:
        """Fetch live data and score it.

        Raises `DataUnavailableError` if live data can't be fetched; pass
        `demo=True` to score deterministic synthetic data instead.
        """
        snapshot = fetch_fundamentals(symbol, demo=demo)
        return self._build_report(snapshot)

    def analyze_snapshot(self, snapshot: FundamentalsSnapshot) -> EvolutionReport:
        """Score a pre-fetched snapshot directly (useful for tests / offline data)."""
        return self._build_report(snapshot)

    def _build_report(self, snapshot: FundamentalsSnapshot) -> EvolutionReport:
        quarterly = compute_quarter_metrics(snapshot.quarters)
        computed_ttm = compute_ttm(snapshot.quarters)
        computed_growth, computed_basis = best_revenue_growth(snapshot.quarters, snapshot.annual)
        reported = snapshot.reported
        profile = profile_for(snapshot.sector)

        # Headline "current" levels come from the data source when it publishes
        # them (so they match what you see on Yahoo); our own statement-based
        # calculation is the fallback and still drives the quarterly trends.
        if reported.revenue_growth is not None:
            growth = reported.revenue_growth
            growth_basis = "Yahoo reported, latest quarter vs same quarter last year"
        else:
            growth, growth_basis = computed_growth, computed_basis
        ttm = _with_reported(computed_ttm, reported)
        if reported.net_margin is not None:
            loss_making = reported.net_margin < 0
        else:
            loss_making = computed_ttm is not None and computed_ttm.net_income < 0

        categories = [
            scoring.score_revenue_growth(quarterly, growth, growth_basis, profile),
            scoring.score_profitability(quarterly, ttm, profile),
            scoring.score_valuation(snapshot.valuation, loss_making, profile),
            scoring.score_debt(quarterly, profile, reported.debt_to_equity, reported.current_ratio),
            scoring.score_cash_flow(quarterly, ttm, profile),
        ]
        comparisons = _compare_sources(quarterly, computed_ttm, computed_growth, reported)

        overall_score = sum(c.score * self.weights[c.name] for c in categories)

        trend_votes = {"Improving": 0, "Stable": 0, "Deteriorating": 0}
        for c in categories:
            trend_votes[c.trend] += 1
        overall_trend = max(trend_votes, key=lambda k: (trend_votes[k], k == "Stable"))

        return EvolutionReport(
            symbol=snapshot.symbol,
            company_name=snapshot.company_name,
            is_demo_data=snapshot.is_demo_data,
            data_notes=snapshot.data_notes,
            categories=categories,
            overall_score=overall_score,
            overall_grade=scoring.grade_for_score(overall_score),
            overall_trend=overall_trend,
            sector=snapshot.sector,
            sector_profile=profile.name,
            comparisons=comparisons,
        )


def _with_reported(ttm, reported: ReportedMetrics):
    """Overlay the data source's published TTM figures onto our own."""
    if ttm is None:
        return None
    overrides = {
        name: value
        for name, value in (
            ("net_margin", reported.net_margin),
            ("roe", reported.roe),
            ("fcf_margin", reported.fcf_margin),
        )
        if value is not None
    }
    if not overrides:
        return ttm
    source = (
        "Yahoo reported (trailing 12 months)"
        if len(overrides) == 3
        else "Yahoo reported where available, else computed (trailing 12 months)"
    )
    return replace(ttm, **overrides, source=source)


def _compare_sources(quarterly, ttm, computed_growth, reported: ReportedMetrics) -> list[SourceComparison]:
    def latest(attr: str):
        return next((getattr(q, attr) for q in reversed(quarterly) if getattr(q, attr) is not None), None)

    rows = [
        ("Revenue growth", "%", computed_growth, reported.revenue_growth),
        ("Net margin", "%", ttm.net_margin if ttm else None, reported.net_margin),
        ("ROE", "%", ttm.roe if ttm else None, reported.roe),
        ("FCF margin", "%", ttm.fcf_margin if ttm else None, reported.fcf_margin),
        ("Debt/equity", "x", latest("debt_to_equity"), reported.debt_to_equity),
        ("Current ratio", "x", latest("current_ratio"), reported.current_ratio),
    ]
    return [
        SourceComparison(metric, unit, computed, rep, "reported" if rep is not None else "computed")
        for metric, unit, computed, rep in rows
    ]


TREND_ICON = {"Improving": "^", "Stable": "-", "Deteriorating": "v"}

# Which metrics to surface as headline numbers under each category, and how
# to render them. (label, metrics_key, suffix) - suffix "%" appends a
# percent sign, "x" a multiple, "s" a text value, "" the raw number.
_HEADLINE_METRICS: dict[str, list[tuple[str, str, str]]] = {
    "Revenue Growth": [
        ("Growth", "latest_growth_pct", "%"),
        ("Measured as", "growth_basis", "s"),
    ],
    "Profitability": [
        ("Net margin", "latest_net_margin_pct", "%"),
        ("ROE", "latest_roe_pct", "%"),
        ("Basis", "basis", "s"),
    ],
    "Valuation": [
        ("Trailing P/E", "trailing_pe", "x"),
        ("Forward P/E", "forward_pe", "x"),
        ("PEG", "peg_ratio", ""),
        ("EV/EBITDA", "ev_to_ebitda", "x"),
        ("P/S", "price_to_sales", "x"),
    ],
    "Debt Levels": [
        ("Debt/Equity", "latest_debt_to_equity", ""),
        ("Current ratio", "latest_current_ratio", ""),
        ("Interest cover", "latest_interest_coverage", "x"),
        ("Debt/EBITDA", "latest_debt_to_ebitda", "x"),
        ("Basis", "basis", "s"),
    ],
    "Cash Flow Trends": [
        ("FCF margin", "latest_fcf_margin_pct", "%"),
        ("Basis", "basis", "s"),
    ],
}


def _format_headline(category: CategoryResult) -> str:
    parts = []
    for label, key, suffix in _HEADLINE_METRICS.get(category.name, []):
        value = category.metrics.get(key)
        if value is None:
            parts.append(f"{label}: n/a")
        elif suffix == "s":
            parts.append(f"{label}: {value}")
        elif suffix == "%":
            parts.append(f"{label}: {value:+.1f}%")
        elif suffix == "x":
            parts.append(f"{label}: {value:.1f}x")
        else:
            parts.append(f"{label}: {value:.2f}")
    return "  |  ".join(parts)


def _format_audit(report: EvolutionReport) -> list[str]:
    lines = ["VALUE CHECK - this model's own calculation vs the figure Yahoo reports",
             "(scoring uses Yahoo's figure when it has one, otherwise our own calculation)"]
    if report.is_demo_data:
        return lines + ["  Demo data has no Yahoo figures to compare against."]
    lines.append(f"  {'Metric':<16}{'Own calc':>10}{'Yahoo':>10}{'Diff':>12}   Used")

    def fmt(value, unit):
        if value is None:
            return "n/a"
        return f"{value * 100:+.1f}%" if unit == "%" else f"{value:.2f}x"

    for c in report.comparisons:
        diff = c.difference
        if diff is None:
            diff_text = "-"
        elif c.unit == "%":
            diff_text = f"{diff * 100:+.1f} pts"
        else:
            diff_text = f"{diff:+.2f}"
        used = "Yahoo" if c.used == "reported" else "own calc"
        lines.append(
            f"  {c.metric:<16}{fmt(c.computed, c.unit):>10}{fmt(c.reported, c.unit):>10}"
            f"{diff_text:>12}   {used}"
        )
    return lines


def format_report(report: EvolutionReport, audit: bool = False) -> str:
    lines = [
        f"{report.company_name} ({report.symbol})",
        f"OVERALL SCORE: {report.overall_score:.1f}/100 (Grade {report.overall_grade})  "
        f"-  Trend: {report.overall_trend}",
    ]
    if report.sector_profile != GENERIC.name:
        lines.append(f"Sector: {report.sector} (scored against {report.sector_profile} thresholds)")
    elif report.sector:
        lines.append(f"Sector: {report.sector} (no sector profile yet - generic thresholds)")
    else:
        lines.append("Sector: unknown (generic thresholds, not sector-adjusted)")
    if report.is_demo_data:
        lines.append(f"[DEMO DATA - not real market data] {'; '.join(report.data_notes)}")
    lines.append("")
    for c in report.categories:
        icon = TREND_ICON.get(c.trend, "-")
        lines.append(f"[{c.grade}] {c.name}: {c.score:.0f}/100  ({icon} {c.trend})")
        headline = _format_headline(c)
        if headline:
            lines.append(f"      {headline}")
        lines.append(f"      how it's scored: {c.detail}")
        lines.append("")
    if audit:
        lines.extend(_format_audit(report))
    return "\n".join(lines).rstrip() + "\n"
