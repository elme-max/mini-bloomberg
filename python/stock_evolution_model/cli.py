"""Command-line interface for the AI-powered stock evolution model."""

from __future__ import annotations

import argparse
import json
import sys

from .fetch import DataUnavailableError
from .model import StockEvolutionModel, format_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock_evolution_model",
        description="Evaluate a company's revenue growth, profitability, valuation, "
        "debt levels, and cash flow trends.",
    )
    parser.add_argument("tickers", nargs="+", help="One or more ticker symbols, e.g. AAPL MSFT")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of text")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use deterministic synthetic data instead of live Yahoo Finance data (no network)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Also print this model's own calculation next to Yahoo's reported figures",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    model = StockEvolutionModel()

    reports = []
    failures = 0
    for ticker in args.tickers:
        try:
            reports.append(model.analyze(ticker, demo=args.demo))
        except DataUnavailableError as exc:
            failures += 1
            print(f"{ticker.upper()}: ERROR - {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps([r.to_dict() for r in reports], indent=2))
    else:
        for report in reports:
            print(format_report(report, audit=args.audit))
            print()

    if failures:
        print(
            f"{failures} ticker(s) failed. Use --demo to see the model on synthetic data.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
