import csv
import math
import random
from datetime import date, timedelta

import pytest

from stock_evolution_model import backtest as bt
from stock_evolution_model.backtest import (
    CATEGORIES,
    ICStats,
    build_observations,
    evaluate,
    fit_weights,
    forward_return,
    load_fundamentals,
    load_prices,
    price_at,
    snapshot_as_of,
    spearman,
    top_minus_bottom,
    walk_forward,
)


# ---------------------------------------------------------------- synthetic world


def make_world(tmp_path, planted=True, n_symbols=60, n_quarters=20, alpha=0.005, seed=7):
    """Companies with a hidden quality `q`. Margins rise with q; when `planted`,
    so does the stock's drift. Everything else is unrelated noise."""

    rng = random.Random(seed)
    start = date(2018, 3, 31)
    fundamentals, prices = [], []
    for i in range(n_symbols):
        symbol = f"S{i:02d}"
        quality = rng.random()
        margin = 0.02 + 0.22 * quality
        growth = rng.uniform(-0.01, 0.03)
        base = rng.uniform(80, 120)
        shares = rng.uniform(1, 50)  # decouples P/E from quality
        debt_factor = rng.uniform(0.5, 4)
        # Only net margin carries the hidden quality; the other statement lines are
        # independent noise so no other category can pick the signal up by accident.
        op_margin, ebitda_margin, ocf_margin = (rng.uniform(0.05, 0.30), rng.uniform(0.10, 0.40),
                                                rng.uniform(0.05, 0.30))
        for k in range(n_quarters):
            revenue = base * (1 + growth) ** k
            fundamentals.append({
                "symbol": symbol, "sector": "",
                "period_end": (start + timedelta(days=91 * k)).isoformat(),
                "revenue": revenue, "gross_profit": revenue * 0.5,
                "operating_income": revenue * op_margin, "net_income": revenue * margin,
                "total_assets": revenue * 8, "total_equity": revenue * 4,
                "total_debt": revenue * debt_factor, "current_assets": revenue * 3,
                "current_liabilities": revenue * rng.uniform(1.5, 4),
                "interest_expense": revenue * 0.01, "ebitda": revenue * ebitda_margin,
                "operating_cash_flow": revenue * ocf_margin, "capex": revenue * 0.05,
                "shares_outstanding": shares,
            })
        price, day = 50.0, date(2018, 1, 1)
        drift = alpha * (quality - 0.5) if planted else 0.0
        while day <= date(2023, 6, 30):
            price *= math.exp(drift + rng.gauss(0, 0.02))
            prices.append({"symbol": symbol, "date": day.isoformat(), "close": price})
            day += timedelta(days=7)

    f_path, p_path = tmp_path / "fundamentals.csv", tmp_path / "prices.csv"
    with open(f_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fundamentals[0]))
        writer.writeheader()
        writer.writerows(fundamentals)
    with open(p_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "close"])
        writer.writeheader()
        writer.writerows(prices)
    return f_path, p_path


@pytest.fixture(scope="module")
def planted_observations(tmp_path_factory):
    f, p = make_world(tmp_path_factory.mktemp("planted"))
    fundamentals, sectors = load_fundamentals(f)
    return build_observations(fundamentals, load_prices(p), sectors)


@pytest.fixture(scope="module")
def noise_observations(tmp_path_factory):
    f, p = make_world(tmp_path_factory.mktemp("noise"), planted=False)
    fundamentals, sectors = load_fundamentals(f)
    return build_observations(fundamentals, load_prices(p), sectors)


# ----------------------------------------------------------------------- statistics


def test_spearman_basics_and_ties():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    # tied ranks are averaged: ranks [1, 2.5, 2.5, 4] vs [1, 2, 3, 4] -> 4.5 / sqrt(4.5 * 5)
    assert spearman([1, 2, 2, 3], [1, 2, 3, 4]) == pytest.approx(math.sqrt(0.9))
    assert spearman([1, 1, 1, 1], [1, 2, 3, 4]) is None  # no variation
    assert spearman([1, 2], [1, 2]) is None  # too few points


def test_top_minus_bottom():
    scores = list(range(10))
    returns = [0.0] * 8 + [0.10, 0.30]  # best two names earn 10% and 30%
    assert top_minus_bottom(scores, returns, 0.2) == pytest.approx(0.20)
    assert top_minus_bottom(scores, list(reversed(returns)), 0.2) == pytest.approx(-0.20)


def test_weight_grid_covers_every_combination_once():
    grid = list(bt._weight_grid(5, 10))
    assert len(grid) == 1001
    assert all(sum(w) == pytest.approx(1.0) for w in grid)
    assert len({tuple(w) for w in grid}) == 1001


# ------------------------------------------------------------- prices and no look-ahead


def test_price_lookup_and_forward_return():
    series = ([date(2024, 1, 1), date(2024, 1, 8), date(2024, 4, 1)], [100.0, 110.0, 150.0])
    assert price_at(series, date(2024, 1, 9)) == 110.0  # last close on/before
    assert price_at(series, date(2023, 12, 31)) is None  # nothing earlier
    assert price_at(series, date(2024, 2, 20)) is None  # too stale to trust
    assert forward_return(series, date(2024, 1, 1), 91) == pytest.approx(0.5)
    assert forward_return(series, date(2024, 1, 1), 400) is None  # window runs past the data


def test_snapshot_only_contains_quarters_reported_by_as_of(tmp_path):
    f, _ = make_world(tmp_path, n_symbols=1, n_quarters=8)
    rows = load_fundamentals(f)[0]["S00"]
    # corrupt the newest quarter so any leakage is obvious
    rows[-1].quarter.revenue = 1e15

    as_of = rows[-1].period_end + timedelta(days=44)  # newest quarter not yet "reported" (lag 45)
    snapshot = snapshot_as_of("S00", rows, None, as_of, lag_days=45)
    assert len(snapshot.quarters) == 7
    assert max(q.revenue for q in snapshot.quarters) < 1e6

    later = snapshot_as_of("S00", rows, None, as_of + timedelta(days=1), lag_days=45)
    assert len(later.quarters) == 8 and later.quarters[-1].revenue == 1e15

    assert snapshot_as_of("S00", rows[:3], None, date(2030, 1, 1), 45) is None  # < 4 quarters


def test_snapshot_never_carries_yahoo_current_figures(tmp_path):
    f, p = make_world(tmp_path, n_symbols=1, n_quarters=8)
    rows = load_fundamentals(f)[0]["S00"]
    snapshot = snapshot_as_of("S00", rows, load_prices(p)["S00"], date(2020, 6, 30), 45)
    assert snapshot.reported.revenue_growth is None and snapshot.reported.net_margin is None
    assert snapshot.valuation.forward_pe is None and snapshot.valuation.peg_ratio is None
    assert snapshot.valuation.price_to_sales is not None  # rebuilt from the as-of price


def test_valuation_uses_price_on_the_as_of_date(tmp_path):
    f, _ = make_world(tmp_path, n_symbols=1, n_quarters=8)
    rows = load_fundamentals(f)[0]["S00"]
    cheap = ([date(2020, 6, 28)], [10.0])
    dear = ([date(2020, 6, 28)], [100.0])
    as_of = date(2020, 6, 30)
    a = snapshot_as_of("S00", rows, cheap, as_of, 45)
    b = snapshot_as_of("S00", rows, dear, as_of, 45)
    assert b.valuation.price_to_sales == pytest.approx(a.valuation.price_to_sales * 10)


# --------------------------------------------------------------------- loaders


def test_loader_rejects_bad_files(tmp_path):
    good, _ = make_world(tmp_path, n_symbols=1, n_quarters=4)
    text = good.read_text()

    missing = tmp_path / "missing.csv"
    missing.write_text(text.replace("net_income", "profit", 1))
    with pytest.raises(ValueError, match="missing column"):
        load_fundamentals(missing)

    lines = text.splitlines()
    header = lines[0].split(",")
    row = lines[1].split(",")
    row[header.index("total_debt")] = ""
    blank = tmp_path / "blank.csv"
    blank.write_text("\n".join([lines[0], ",".join(row)] + lines[2:]))
    with pytest.raises(ValueError, match=r"line 2.*total_debt"):
        load_fundamentals(blank)  # a blank is an error, never a silent zero

    prices = tmp_path / "prices.csv"
    prices.write_text("symbol,date,close\nAAA,2024-01-01,-5\n")
    with pytest.raises(ValueError, match="positive"):
        load_prices(prices)


# ---------------------------------------------------------- finding the real signal


def test_backtest_finds_the_planted_signal(planted_observations):
    assert len({o.as_of for o in planted_observations}) >= 12

    stats = evaluate(planted_observations)
    profitability = stats["Profitability"]
    assert profitability.mean_ic > 0.15 and profitability.t_stat > 2
    assert profitability.mean_spread > 0  # top fifth really did beat the bottom fifth
    for name in CATEGORIES:
        if name != "Profitability":
            assert abs(stats[name].mean_ic or 0) < profitability.mean_ic
    assert stats["Overall (equal weights)"].mean_ic > 0


def test_backtest_finds_nothing_in_pure_noise(noise_observations):
    stats = evaluate(noise_observations)
    for name in CATEGORIES:
        assert abs(stats[name].mean_ic or 0) < 0.12, name


def test_fitted_weights_favor_the_category_that_works(planted_observations):
    weights = fit_weights(planted_observations)
    assert max(weights, key=weights.get) == "Profitability"
    assert sum(weights.values()) == pytest.approx(1.0)
    # shrinkage keeps every category in play
    assert min(weights.values()) >= 0.5 * (1 / len(CATEGORIES)) - 1e-9


def test_walk_forward_is_chronological_and_wins_out_of_sample(planted_observations):
    result = walk_forward(planted_observations)
    assert result.train_end < result.test_start
    assert result.n_train_dates >= 4 and result.n_test_dates >= 4
    assert result.fitted_test.mean_ic > result.equal_test.mean_ic
    assert result.adopt


def test_noise_world_does_not_justify_new_weights(noise_observations):
    result = walk_forward(noise_observations)
    # whatever the fit found in-sample, adoption requires a real out-of-sample win
    assert result.adopt == (
        result.n_train_dates >= 4 and result.n_test_dates >= 4
        and result.fitted_test.mean_ic > result.equal_test.mean_ic + 0.01
        and result.fitted_test.mean_ic > 0
    )


def test_verdict_rules():
    good = ICStats(0.08, 2.0, 8, 0.02)
    flat = ICStats(0.01, 0.3, 8, 0.0)
    assert bt._verdict(2, 8, flat, good)[0] is False  # too few training dates
    assert bt._verdict(8, 2, flat, good)[0] is False  # too few test dates
    assert bt._verdict(8, 8, good, flat)[0] is False  # fitted lost out-of-sample
    assert bt._verdict(8, 8, flat, ICStats(-0.05, -1, 8, 0))[0] is False  # beat equal? no, negative
    assert bt._verdict(8, 8, flat, good)[0] is True
    assert bt._verdict(8, 8, flat, ICStats(None, None, 0, None))[0] is False


# ------------------------------------------------------------- end to end and the CLI


def test_run_backtest_report_and_warnings(tmp_path):
    f, p = make_world(tmp_path, n_symbols=12, n_quarters=10)
    result = bt.run_backtest(f, p, min_names=5)
    text = bt.format_backtest(result)
    assert "BACKTEST" in text and "Mean IC" in text and "Verdict:" in text
    assert any("companies per date" in w for w in result.warnings)  # 12 names is a small universe

    data = bt.result_to_dict(result)
    assert data["observations"] == result.n_observations
    assert set(data["stats"]) == {*CATEGORIES, "Overall (equal weights)"}


def test_cli_run_and_empty_input(tmp_path, capsys):
    f, p = make_world(tmp_path, n_symbols=8, n_quarters=10)
    assert bt.main(["run", "--fundamentals", str(f), "--prices", str(p), "--json"]) == 0
    assert '"observations"' in capsys.readouterr().out

    (tmp_path / "short").mkdir()
    short, _ = make_world(tmp_path / "short", n_symbols=2, n_quarters=2)  # < 4 quarters: nothing to score
    assert bt.main(["run", "--fundamentals", str(short), "--prices", str(p)]) == 1
    assert "No usable observations" in capsys.readouterr().out

    assert bt.main(["run", "--fundamentals", str(tmp_path / "nope.csv"), "--prices", str(p)]) == 1
    assert "ERROR" in capsys.readouterr().err


# ----------------------------------------------------------------- Yahoo export


def _patch_yahoo(monkeypatch, failing=()):
    pd = pytest.importorskip("pandas")
    from types import SimpleNamespace

    import stock_evolution_model.fetch as fetch_module
    from .test_fetch import FakeTicker

    class FakeWithHistory(FakeTicker):
        def __init__(self, symbol):
            if symbol in failing:
                raise RuntimeError("boom")
            super().__init__(symbol)

        def get_info(self):
            return {**super().get_info(), "sharesOutstanding": 10.0}

        def history(self, period="max", auto_adjust=True):
            days = pd.date_range("2024-01-07", periods=100, freq="W")
            return pd.DataFrame({"Close": [50 + 0.5 * i for i in range(100)]}, index=days)

    monkeypatch.setattr(fetch_module, "yf", SimpleNamespace(Ticker=FakeWithHistory))


def test_export_writes_csvs_the_backtest_can_read(tmp_path, monkeypatch):
    _patch_yahoo(monkeypatch)
    summary = bt.export_yahoo_history(["fake"], tmp_path)
    assert summary.exported == {"FAKE": 6} and not summary.errors

    fundamentals, sectors = load_fundamentals(tmp_path / "fundamentals.csv")
    prices = load_prices(tmp_path / "prices.csv")
    assert len(fundamentals["FAKE"]) == 6
    assert fundamentals["FAKE"][0].shares == 10.0 and sectors["FAKE"] == "Technology"
    assert len(prices["FAKE"][0]) == 100

    snapshot = snapshot_as_of("FAKE", fundamentals["FAKE"], prices["FAKE"], date(2025, 9, 30), 45, "Technology")
    assert len(snapshot.quarters) == 6 and snapshot.valuation.price_to_sales is not None


def test_export_reports_failures_and_keeps_going(tmp_path, monkeypatch):
    _patch_yahoo(monkeypatch, failing={"BAD"})
    summary = bt.export_yahoo_history(["BAD", "FAKE"], tmp_path)
    assert "BAD" in summary.errors and "FAKE" in summary.exported


def test_export_cli_warns_about_yahoo_history_limits(tmp_path, monkeypatch, capsys):
    _patch_yahoo(monkeypatch)
    assert bt.main(["export", "FAKE", "--out", str(tmp_path / "h")]) == 0
    assert "only ~4-5 recent quarters" in capsys.readouterr().out
    # one company can be scored but not ranked: say so instead of printing n/a tables
    assert bt.main(["run", "--fundamentals", str(tmp_path / "h" / "fundamentals.csv"),
                    "--prices", str(tmp_path / "h" / "prices.csv")]) == 1
    out = capsys.readouterr().out
    assert "No statistics computed" in out and "no as-of date had at least 5 companies" in out
    assert "Mean IC" not in out and "clipped" not in out.lower().replace("clipped =", "")
