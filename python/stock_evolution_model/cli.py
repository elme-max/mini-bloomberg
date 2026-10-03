"""Command-line interface for the AI-powered stock evolution model."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from .cache import DEFAULT_TTL_HOURS, SnapshotCache
from .compare import SORT_CHOICES, format_table, sort_reports, write_csv
from .fetch import DataUnavailableError
from .model import StockEvolutionModel, format_report


def read_tickers_file(path: str | Path) -> list[str]:
    """Tickers from a text file: separated by whitespace and/or commas, `#` starts a comment."""
    text = Path(path).read_text()
    tickers: list[str] = []
    for line in text.splitlines():
        tickers.extend(t for t in re.split(r"[\s,;]+", line.split("#", 1)[0]) if t)
    return tickers


def collect_tickers(from_args: list[str], file_path: str | None) -> list[str]:
    """Command-line tickers followed by file tickers: upper-cased, duplicates dropped, order kept."""
    combined = [*from_args, *(read_tickers_file(file_path) if file_path else [])]
    seen: dict[str, None] = {}
    for ticker in combined:
        seen.setdefault(ticker.strip().upper(), None)
    return [t for t in seen if t]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock_evolution_model",
        description="Evaluate a company's revenue growth, profitability, valuation, "
        "debt levels, and cash flow trends.",
    )
    parser.add_argument("tickers", nargs="*", help="Ticker symbols, e.g. AAPL MSFT (or use --tickers-file)")
    parser.add_argument(
        "--tickers-file",
        metavar="FILE",
        help="Also read tickers from FILE (separated by spaces, commas or lines; # starts a comment)",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of text")
    output.add_argument(
        "--table",
        action="store_true",
        help="Print one ranked comparison table instead of a full report per company",
    )
    parser.add_argument(
        "--sort",
        choices=SORT_CHOICES,
        default="score",
        help="Order for --table and --csv: overall score (default), ticker, or one category",
    )
    parser.add_argument("--csv", metavar="FILE", help="Also write a ranked comparison to FILE as CSV")
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
    parser.add_argument(
        "--no-cache", action="store_true", help="Always fetch from Yahoo; don't read or write the cache"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Ignore cached data for this run but store the fresh result"
    )
    parser.add_argument("--cache-dir", metavar="DIR", help="Cache location (default ~/.cache/stock_evolution_model)")
    parser.add_argument(
        "--cache-hours",
        type=float,
        default=DEFAULT_TTL_HOURS,
        metavar="H",
        help=f"How long fetched data stays fresh (default {DEFAULT_TTL_HOURS:g} hours)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        metavar="SECONDS",
        help="Pause between live Yahoo requests to avoid rate limiting (default 0.5; skipped for cached data)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        tickers = collect_tickers(args.tickers, args.tickers_file)
    except OSError as exc:
        parser.error(f"can't read tickers file: {exc}")
    if not tickers:
        parser.error("give at least one ticker, or --tickers-file")

    cache = None if args.demo or args.no_cache else SnapshotCache(args.cache_dir, args.cache_hours)
    model = StockEvolutionModel(cache=cache)

    reports = []
    failures = 0
    used_network = False
    for ticker in tickers:
        if used_network and args.delay > 0:
            time.sleep(args.delay)  # be polite to Yahoo between live requests
        stores_before = cache.stores if cache else 0
        try:
            reports.append(model.analyze(ticker, demo=args.demo, refresh=args.refresh))
            used_network = not args.demo and (cache is None or cache.stores > stores_before)
        except DataUnavailableError as exc:
            failures += 1
            used_network = True  # a failed lookup still hit the network
            print(f"{ticker}: ERROR - {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps([r.to_dict() for r in reports], indent=2))
    elif args.table:
        if reports:
            print(format_table(reports, args.sort), end="")
    else:
        for report in reports:
            print(format_report(report, audit=args.audit))
            print()

    if args.csv and reports:
        try:
            rows = write_csv(reports, args.csv, args.sort)
        except OSError as exc:
            print(f"ERROR - can't write {args.csv}: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote {rows} row(s) to {args.csv}", file=sys.stderr)

    if failures:
        print(
            f"{failures} ticker(s) failed. Use --demo to see the model on synthetic data.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
