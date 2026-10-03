"""Side-by-side ranking of several companies, as a text table or a CSV file."""

from __future__ import annotations

import csv
from pathlib import Path

from .types import EvolutionReport

CATEGORY_KEYS = {
    "growth": "Revenue Growth",
    "profitability": "Profitability",
    "valuation": "Valuation",
    "debt": "Debt Levels",
    "cashflow": "Cash Flow Trends",
}
SORT_CHOICES = ["score", "ticker", *CATEGORY_KEYS]

_TABLE_HEADERS = {
    "Revenue Growth": "Growth",
    "Profitability": "Profit",
    "Valuation": "Value",
    "Debt Levels": "Debt",
    "Cash Flow Trends": "Cash",
}

# (csv column, category, metrics key): headline figures exported alongside the scores
_CSV_METRICS = [
    ("revenue_growth_pct", "Revenue Growth", "latest_growth_pct"),
    ("net_margin_pct", "Profitability", "latest_net_margin_pct"),
    ("roe_pct", "Profitability", "latest_roe_pct"),
    ("fcf_margin_pct", "Cash Flow Trends", "latest_fcf_margin_pct"),
    ("debt_to_equity", "Debt Levels", "latest_debt_to_equity"),
    ("current_ratio", "Debt Levels", "latest_current_ratio"),
    ("interest_coverage", "Debt Levels", "latest_interest_coverage"),
    ("debt_to_ebitda", "Debt Levels", "latest_debt_to_ebitda"),
    ("trailing_pe", "Valuation", "trailing_pe"),
    ("forward_pe", "Valuation", "forward_pe"),
    ("peg_ratio", "Valuation", "peg_ratio"),
    ("ev_to_ebitda", "Valuation", "ev_to_ebitda"),
    ("price_to_sales", "Valuation", "price_to_sales"),
]


def _category(report: EvolutionReport, name: str):
    return next(c for c in report.categories if c.name == name)


def sort_reports(reports: list[EvolutionReport], key: str = "score") -> list[EvolutionReport]:
    """Best first by overall score or by one category; `ticker` sorts A-Z.
    Ties are broken alphabetically so the order is stable."""

    if key == "ticker":
        return sorted(reports, key=lambda r: r.symbol)
    if key == "score":
        return sorted(reports, key=lambda r: (-r.overall_score, r.symbol))
    if key in CATEGORY_KEYS:
        name = CATEGORY_KEYS[key]
        return sorted(reports, key=lambda r: (-_category(r, name).score, r.symbol))
    raise ValueError(f"unknown sort key {key!r}; choose from {', '.join(SORT_CHOICES)}")


def format_table(reports: list[EvolutionReport], sort: str = "score") -> str:
    ordered = sort_reports(reports, sort)
    sector_width = max([len("Sector"), *(len(r.sector or "-") for r in ordered)])
    categories = list(_TABLE_HEADERS)

    header = (
        f"{'Rank':>4}  {'Ticker':<8}{'Score':>6}  {'Grade':<5}  {'Trend':<13}  {'Sector':<{sector_width}}"
        + "".join(f"{_TABLE_HEADERS[c]:>8}" for c in categories)
    )
    lines = [header, "-" * len(header)]
    for rank, report in enumerate(ordered, start=1):
        ticker = report.symbol + ("*" if report.is_demo_data else "")
        scores = "".join(f"{_category(report, c).score:>8.1f}" for c in categories)
        lines.append(
            f"{rank:>4}  {ticker:<8}{report.overall_score:>6.1f}  {report.overall_grade:<5}  "
            f"{report.overall_trend:<13}  {(report.sector or '-'):<{sector_width}}{scores}"
        )
    order_text = {"score": "overall score", "ticker": "ticker"}.get(sort, f"{CATEGORY_KEYS.get(sort)} score")
    lines += ["", f"{len(ordered)} compan{'y' if len(ordered) == 1 else 'ies'}, ranked by {order_text} "
                  "(scores 0-100, higher is better)."]
    if any(r.is_demo_data for r in ordered):
        lines.append("* = synthetic demo data, not real market data.")
    return "\n".join(lines) + "\n"


def csv_rows(reports: list[EvolutionReport], sort: str = "score") -> list[dict]:
    rows = []
    for rank, report in enumerate(sort_reports(reports, sort), start=1):
        row: dict = {
            "rank": rank,
            "symbol": report.symbol,
            "company": report.company_name,
            "sector": report.sector or "",
            "sector_profile": report.sector_profile,
            "overall_score": f"{report.overall_score:.2f}",
            "overall_grade": report.overall_grade,
            "overall_trend": report.overall_trend,
            "demo_data": report.is_demo_data,
        }
        for key, name in CATEGORY_KEYS.items():
            category = _category(report, name)
            row[f"{key}_score"] = f"{category.score:.2f}"
            row[f"{key}_grade"] = category.grade
            row[f"{key}_trend"] = category.trend
        for column, name, metric in _CSV_METRICS:
            value = _category(report, name).metrics.get(metric)
            row[column] = "" if value is None else f"{value:.2f}"
        rows.append(row)
    return rows


def write_csv(reports: list[EvolutionReport], path: str | Path, sort: str = "score") -> int:
    """Write one row per company; returns the number of rows written."""
    rows = csv_rows(reports, sort)
    columns = list(rows[0]) if rows else ["rank", "symbol"]
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
