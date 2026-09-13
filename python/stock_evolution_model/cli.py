"""Command-line interface for the AI-powered stock evolution model."""

from __future__ import annotations

import argparse
import json
import sys

from .model import StockEvolutionModel, format_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock_evolution_model",
        description="Evaluate a company's revenue growth, profitability, valuation, "
        "debt levels, and cash flow trends.",
    )
    parser.add_argument("tickers", nargs="+", help="One or more ticker symbols, e.g. AAPL MSFT")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    model = StockEvolutionModel()

    reports = [model.analyze(ticker) for ticker in args.tickers]

    if args.json:
        print(json.dumps([r.to_dict() for r in reports], indent=2))
    else:
        for report in reports:
            print(format_report(report))
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
