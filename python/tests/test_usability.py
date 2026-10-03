import csv
import json
import time
from types import SimpleNamespace

import pytest

from stock_evolution_model import StockEvolutionModel, cli, format_report
from stock_evolution_model.cache import (
    CACHE_VERSION,
    SnapshotCache,
    snapshot_from_dict,
    snapshot_to_dict,
)
from stock_evolution_model.compare import csv_rows, format_table, sort_reports, write_csv
from stock_evolution_model.demo_data import generate_demo_fundamentals
from stock_evolution_model.fetch import DataUnavailableError, fetch_fundamentals
from stock_evolution_model.types import ReportedMetrics


def reports_for(*symbols):
    model = StockEvolutionModel()
    return [model.analyze_snapshot(generate_demo_fundamentals(s)) for s in symbols]


def full_snapshot():
    """A live-style snapshot exercising every field that gets cached."""
    snapshot = generate_demo_fundamentals("MSFT")
    snapshot.is_demo_data = False
    snapshot.annual = snapshot.quarters[:2]
    snapshot.reported = ReportedMetrics(revenue_growth=0.1, net_margin=0.2, debt_to_equity=1.5)
    return snapshot


# --------------------------------------------------------------- tickers from a file


def test_tickers_file_handles_separators_comments_and_duplicates(tmp_path):
    path = tmp_path / "watch.txt"
    path.write_text("# my list\naapl, msft   nvda\nTSLA # trailing comment\njpm; amzn\n\nAAPL\n")
    assert cli.read_tickers_file(path) == ["aapl", "msft", "nvda", "TSLA", "jpm", "amzn", "AAPL"]
    assert cli.collect_tickers(["goog", "msft"], str(path)) == [
        "GOOG", "MSFT", "AAPL", "NVDA", "TSLA", "JPM", "AMZN",
    ]
    assert cli.collect_tickers([], None) == []


# ----------------------------------------------------------------------------- cache


def test_cache_roundtrip_preserves_every_field(tmp_path):
    cache = SnapshotCache(tmp_path)
    original = full_snapshot()
    cache.put("msft", original)

    cached = cache.get("MSFT")
    assert cached is not None and cache.hits == 1 and cache.stores == 1
    assert "served from cache" in cached.data_notes[-1]
    cached.data_notes = original.data_notes  # only the freshness note differs
    assert cached == original
    assert snapshot_from_dict(snapshot_to_dict(original)) == original


def test_cache_expires_after_ttl(tmp_path):
    clock = {"now": 1_000_000.0}
    cache = SnapshotCache(tmp_path, ttl_hours=2, now=lambda: clock["now"])
    cache.put("MSFT", full_snapshot())

    clock["now"] += 1.9 * 3600
    assert cache.get("MSFT") is not None
    clock["now"] += 0.2 * 3600
    assert cache.get("MSFT") is None  # 2.1 hours old


def test_cache_age_is_described_in_the_note(tmp_path):
    clock = {"now": 5_000.0}
    cache = SnapshotCache(tmp_path, now=lambda: clock["now"])
    cache.put("MSFT", full_snapshot())
    clock["now"] += 20 * 60
    assert "20 min ago" in cache.get("MSFT").data_notes[-1]
    clock["now"] += 3 * 3600
    assert "3.3 h ago" in cache.get("MSFT").data_notes[-1]


def test_cache_never_stores_demo_data(tmp_path):
    cache = SnapshotCache(tmp_path)
    cache.put("AAPL", generate_demo_fundamentals("AAPL"))
    assert cache.stores == 0 and cache.get("AAPL") is None and not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.write_text("{not json"),
        lambda p: p.write_text(json.dumps({"version": CACHE_VERSION + 1})),
        lambda p: p.write_text(json.dumps({**json.loads(p.read_text()), "symbol": "OTHER"})),
        lambda p: p.write_text(json.dumps({**json.loads(p.read_text()), "fetched_at": "yesterday"})),
        lambda p: p.write_text(json.dumps({**json.loads(p.read_text()), "fetched_at": 9e12})),  # from the future
        lambda p: p.write_text(json.dumps({**json.loads(p.read_text()), "snapshot": {"symbol": "MSFT"}})),
    ],
    ids=["corrupt", "version", "symbol", "timestamp", "clock-skew", "schema"],
)
def test_bad_cache_files_are_just_misses(tmp_path, mutate):
    cache = SnapshotCache(tmp_path)
    cache.put("MSFT", full_snapshot())
    mutate(cache.path_for("MSFT"))
    assert cache.get("MSFT") is None


def test_cache_paths_are_safe_and_writes_are_atomic(tmp_path):
    cache = SnapshotCache(tmp_path / "nested" / "dir")
    for symbol in ("BRK-B", "^GSPC", "../evil", "BF.B"):
        assert cache.path_for(symbol).parent == cache.directory
    cache.put("MSFT", full_snapshot())
    assert [p.name for p in cache.directory.iterdir()] == ["MSFT.json"]  # no leftover .tmp


def test_unwritable_cache_does_not_break_analysis(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    cache = SnapshotCache(blocker / "sub")
    cache.put("MSFT", full_snapshot())  # must not raise
    assert cache.stores == 0 and cache.get("MSFT") is None


# ---------------------------------------------------------- fetch + cache together


@pytest.fixture
def counting_yahoo(monkeypatch):
    pd = pytest.importorskip("pandas")  # noqa: F841 - required by the fake ticker
    import stock_evolution_model.fetch as fetch_module
    from .test_fetch import FakeTicker

    calls = []

    def ticker(symbol):
        calls.append(symbol)
        return FakeTicker(symbol)

    monkeypatch.setattr(fetch_module, "yf", SimpleNamespace(Ticker=ticker))
    return calls


def test_second_fetch_comes_from_cache_even_offline(tmp_path, counting_yahoo, monkeypatch):
    import stock_evolution_model.fetch as fetch_module

    cache = SnapshotCache(tmp_path)
    first = fetch_fundamentals("fake", cache=cache)
    assert counting_yahoo == ["FAKE"] and cache.stores == 1 and not first.data_notes

    monkeypatch.setattr(fetch_module, "yf", None)  # now there is no yfinance at all
    second = fetch_fundamentals("fake", cache=cache)
    assert second.company_name == "Fake Corp" and "served from cache" in second.data_notes[-1]
    assert counting_yahoo == ["FAKE"]  # no further request


def test_refresh_bypasses_the_cache_but_updates_it(tmp_path, counting_yahoo):
    cache = SnapshotCache(tmp_path)
    fetch_fundamentals("fake", cache=cache)
    fetch_fundamentals("fake", cache=cache, refresh=True)
    assert counting_yahoo == ["FAKE", "FAKE"] and cache.stores == 2


def test_failed_and_demo_fetches_are_not_cached(tmp_path, monkeypatch):
    import stock_evolution_model.fetch as fetch_module

    cache = SnapshotCache(tmp_path)
    monkeypatch.setattr(fetch_module, "yf", None)
    with pytest.raises(DataUnavailableError):
        fetch_fundamentals("AAPL", cache=cache)
    fetch_fundamentals("AAPL", demo=True, cache=cache)
    assert cache.stores == 0 and not list(tmp_path.glob("*.json"))


def test_report_mentions_cached_data(tmp_path, counting_yahoo):
    model = StockEvolutionModel(cache=SnapshotCache(tmp_path))
    assert "Data:" not in format_report(model.analyze("fake"))
    assert "Data: served from cache" in format_report(model.analyze("fake"))


# ------------------------------------------------------------------ table and CSV


def test_ranking_orders_and_tie_breaks():
    reports = reports_for("AAPL", "NVDA", "TSLA", "JPM")
    by_score = [r.symbol for r in sort_reports(reports, "score")]
    assert by_score == [r.symbol for r in sorted(reports, key=lambda r: (-r.overall_score, r.symbol))]
    assert [r.symbol for r in sort_reports(reports, "ticker")] == ["AAPL", "JPM", "NVDA", "TSLA"]

    debt = [next(c for c in r.categories if c.name == "Debt Levels").score for r in sort_reports(reports, "debt")]
    assert debt == sorted(debt, reverse=True)

    twin = reports_for("AAPL")[0]
    twin_b = reports_for("AAPL")[0]
    twin_b.symbol = "AAAA"
    assert [r.symbol for r in sort_reports([twin, twin_b], "score")] == ["AAAA", "AAPL"]
    with pytest.raises(ValueError, match="unknown sort key"):
        sort_reports(reports, "vibes")


def test_table_layout():
    reports = reports_for("AAPL", "NVDA", "JPM")
    table = format_table(reports)
    lines = table.splitlines()
    assert lines[0].split()[:3] == ["Rank", "Ticker", "Score"]
    ranked = [line.split()[1] for line in lines[2:5]]
    assert ranked == [r.symbol + "*" for r in sort_reports(reports)]
    assert "3 companies, ranked by overall score" in table and "synthetic demo data" in table
    assert "1 company," in format_table(reports[:1])
    assert "Debt Levels score" in format_table(reports, "debt")


def test_csv_has_ranked_rows_and_two_decimal_values(tmp_path):
    reports = reports_for("AAPL", "NVDA", "JPM")
    path = tmp_path / "out.csv"
    assert write_csv(reports, path, "score") == 3

    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["symbol"] for r in rows] == [r.symbol for r in sort_reports(reports)]
    assert [r["rank"] for r in rows] == ["1", "2", "3"]
    assert rows[0]["demo_data"] == "True" and rows[0]["overall_grade"] in "ABCDF"
    for column in ("overall_score", "growth_score", "net_margin_pct", "trailing_pe"):
        assert all(len(r[column].split(".")[1]) == 2 for r in rows if r[column]), column
    jpm = next(r for r in rows if r["symbol"] == "JPM")
    assert jpm["current_ratio"] == "" and jpm["interest_coverage"] == ""  # not used for banks
    assert csv_rows([]) == []


# ------------------------------------------------------------------------- the CLI


def test_cli_table_csv_and_file(tmp_path, capsys):
    watch = tmp_path / "watch.txt"
    watch.write_text("nvda\njpm  # bank\n")
    out = tmp_path / "ranked.csv"

    assert cli.main(["AAPL", "--tickers-file", str(watch), "--demo", "--table", "--csv", str(out)]) == 0
    captured = capsys.readouterr()
    assert "Rank" in captured.out
    assert "OVERALL SCORE" not in captured.out  # table replaces the per-company reports
    assert f"Wrote 3 row(s) to {out}" in captured.err
    assert len(list(csv.DictReader(open(out)))) == 3


def test_cli_rejects_missing_input_and_conflicting_formats(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2 and "at least one ticker" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(["AAPL", "--json", "--table"])
    with pytest.raises(SystemExit):
        cli.main(["AAPL", "--tickers-file", str(tmp_path / "missing.txt")])
    assert "can't read tickers file" in capsys.readouterr().err


def test_cli_csv_write_failure_is_reported(tmp_path, capsys):
    assert cli.main(["AAPL", "--demo", "--csv", str(tmp_path / "no" / "such" / "dir.csv")]) == 1
    assert "can't write" in capsys.readouterr().err


def test_cli_pauses_between_live_requests_only(tmp_path, counting_yahoo, monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    args = ["fakea", "fakeb", "fakec", "--cache-dir", str(tmp_path), "--delay", "0.75", "--table"]

    assert cli.main(args) == 0
    assert sleeps == [0.75, 0.75]  # between three live fetches
    assert counting_yahoo == ["FAKEA", "FAKEB", "FAKEC"]

    sleeps.clear()
    assert cli.main(args) == 0  # everything now cached: no requests, no pauses
    assert sleeps == [] and len(counting_yahoo) == 3

    sleeps.clear()
    assert cli.main([*args, "--refresh"]) == 0
    assert len(sleeps) == 2 and len(counting_yahoo) == 6

    sleeps.clear()
    assert cli.main(["fakea", "fakeb", "--no-cache", "--delay", "0.1", "--table"]) == 0
    assert sleeps == [0.1]


def test_cli_demo_mode_never_sleeps_or_caches(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    assert cli.main(["AAPL", "MSFT", "--demo", "--cache-dir", str(tmp_path)]) == 0
    assert sleeps == [] and not list(tmp_path.iterdir())


def test_cli_failed_ticker_still_pauses_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    import stock_evolution_model.fetch as fetch_module

    monkeypatch.setattr(fetch_module, "yf", None)
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    assert cli.main(["AAA", "BBB", "--cache-dir", str(tmp_path), "--delay", "1"]) == 1
    err = capsys.readouterr().err
    assert "AAA: ERROR" in err and "BBB: ERROR" in err and sleeps == [1.0]
