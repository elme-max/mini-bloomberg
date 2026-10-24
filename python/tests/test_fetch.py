from types import SimpleNamespace

import pytest

pd = pytest.importorskip("pandas")

import stock_evolution_model.fetch as fetch_module
from stock_evolution_model import StockEvolutionModel
from stock_evolution_model.fetch import DataUnavailableError, fetch_fundamentals


def _frame(rows: dict[str, list[float]], dates: list[str]):
    # yfinance returns statements newest-first, one column per period.
    return pd.DataFrame(rows, index=None).T.set_axis(pd.to_datetime(dates), axis=1)


QUARTER_DATES = ["2025-06-30", "2025-03-31", "2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31"]
ANNUAL_DATES = ["2024-12-31", "2023-12-31"]


class FakeTicker:
    def __init__(self, symbol):
        n = len(QUARTER_DATES)
        revenue = [100 + 5 * (n - i) for i in range(n)]  # newest first, growing
        self.quarterly_financials = _frame(
            {
                "Total Revenue": revenue,
                "Gross Profit": [r * 0.5 for r in revenue],
                "Operating Income": [r * 0.2 for r in revenue],
                "Net Income": [r * 0.15 for r in revenue],
                "EBITDA": [r * 0.25 for r in revenue],
                "Interest Expense": [2.0] * n,
            },
            QUARTER_DATES,
        )
        self.quarterly_balance_sheet = _frame(
            {
                "Total Assets": [500.0] * n,
                "Stockholders Equity": [250.0] * n,
                "Total Debt": [100.0] * n,
                "Current Assets": [150.0] * n,
                "Current Liabilities": [100.0] * n,
            },
            QUARTER_DATES,
        )
        self.quarterly_cashflow = _frame(
            {"Operating Cash Flow": [30.0] * n, "Capital Expenditure": [-8.0] * n},
            QUARTER_DATES,
        )
        self.financials = _frame(
            {"Total Revenue": [480.0, 400.0], "Net Income": [70.0, 55.0]}, ANNUAL_DATES
        )
        self.balance_sheet = _frame({"Total Assets": [500.0, 480.0]}, ANNUAL_DATES)
        self.cashflow = _frame({"Operating Cash Flow": [120.0, 100.0]}, ANNUAL_DATES)

    def get_info(self):
        return {
            "longName": "Fake Corp",
            "sector": "Technology",
            "revenueGrowth": 0.12,
            "profitMargins": 0.20,
            "returnOnEquity": 0.35,
            "debtToEquity": 150.0,  # Yahoo publishes this as a percentage
            "currentRatio": 1.4,
            "freeCashflow": 60.0,
            "totalRevenue": 600.0,
            "trailingPE": 20.0,
            "forwardPE": 18.0,
            "pegRatio": 1.2,
            "enterpriseToEbitda": 12.0,
            "priceToSalesTrailing12Months": 3.0,
        }


def test_live_path_parses_statements(monkeypatch):
    monkeypatch.setattr(fetch_module, "yf", SimpleNamespace(Ticker=FakeTicker))

    snapshot = fetch_fundamentals("fake")

    assert snapshot.is_demo_data is False
    assert snapshot.symbol == "FAKE"
    assert snapshot.company_name == "Fake Corp"
    assert len(snapshot.quarters) == 6
    revenues = [q.revenue for q in snapshot.quarters]
    assert revenues == sorted(revenues)  # oldest -> newest
    assert snapshot.quarters[-1].capex == 8.0  # sign normalized
    assert snapshot.quarters[-1].interest_expense == 2.0
    assert [a.revenue for a in snapshot.annual] == [400.0, 480.0]
    assert snapshot.sector == "Technology"
    assert snapshot.reported.revenue_growth == 0.12
    assert snapshot.reported.debt_to_equity == pytest.approx(1.5)
    assert snapshot.reported.fcf_margin == pytest.approx(0.10)
    assert snapshot.valuation.forward_pe == 18.0
    assert snapshot.valuation.ev_to_ebitda == 12.0


def test_live_path_scores_end_to_end(monkeypatch):
    monkeypatch.setattr(fetch_module, "yf", SimpleNamespace(Ticker=FakeTicker))

    report = StockEvolutionModel().analyze("fake")

    assert report.is_demo_data is False
    assert 0 <= report.overall_score <= 100
    growth = next(c for c in report.categories if c.name == "Revenue Growth")
    assert growth.metrics["latest_growth_pct"] == 12.0
    assert growth.metrics["growth_basis"].startswith("Yahoo reported")
    assert report.sector_profile == "Technology"


def test_empty_statements_raise(monkeypatch):
    class EmptyTicker:
        quarterly_financials = pd.DataFrame()

        def get_info(self):
            return {}

    monkeypatch.setattr(fetch_module, "yf", SimpleNamespace(Ticker=lambda s: EmptyTicker()))

    with pytest.raises(DataUnavailableError, match="no quarterly income statement"):
        fetch_fundamentals("NOPE")


def test_missing_yfinance_raises(monkeypatch):
    monkeypatch.setattr(fetch_module, "yf", None)

    with pytest.raises(DataUnavailableError, match="not installed"):
        fetch_fundamentals("AAPL")


# ------------------------------------------------- fragile parsing paths in fetch.py


def _ticker(quarterly_financials, balance=None, cashflow=None, info=None, annual=None, info_error=None):
    """Minimal yfinance.Ticker stand-in built from the given frames."""

    class Ticker:
        def __init__(self, symbol):
            self.quarterly_financials = quarterly_financials
            self.quarterly_balance_sheet = balance if balance is not None else pd.DataFrame()
            self.quarterly_cashflow = cashflow if cashflow is not None else pd.DataFrame()

        @property
        def financials(self):
            if isinstance(annual, Exception):
                raise annual
            return annual if annual is not None else pd.DataFrame()

        balance_sheet = pd.DataFrame()
        cashflow = pd.DataFrame()

        def get_info(self):
            if info_error:
                raise info_error
            return info or {}

    return Ticker


def _use(monkeypatch, ticker_cls):
    monkeypatch.setattr(fetch_module, "yf", SimpleNamespace(Ticker=ticker_cls))


Q3 = ["2025-06-30", "2025-03-31", "2024-12-31"]


def test_valuation_rejects_nan_infinity_booleans_and_text():
    build = fetch_module._build_valuation
    for bad in (float("nan"), float("inf"), float("-inf"), True, "Infinity", None):
        assert build({"trailingPE": bad}).trailing_pe is None, bad
    assert build({"trailingPE": 25}).trailing_pe == 25.0  # plain ints are fine

    # fall back to the secondary key when the first is missing or junk
    assert build({"regularMarketPrice": 101.5}).share_price == 101.5
    assert build({"currentPrice": 99.0, "regularMarketPrice": 101.5}).share_price == 99.0
    assert build({"pegRatio": float("nan"), "trailingPegRatio": 1.7}).peg_ratio == 1.7


def test_value_at_falls_back_on_missing_nan_and_text():
    row = pd.Series({"a": 5.0, "b": float("nan"), "c": "n/a", "d": None})
    value_at = fetch_module._value_at
    assert value_at(row, "a") == 5.0
    assert value_at(row, "b", default=-1.0) == -1.0
    assert value_at(row, "c", default=-1.0) == -1.0
    assert value_at(row, "d", default=-1.0) == -1.0
    assert value_at(row, "missing", default=-1.0) == -1.0
    assert value_at(None, "a", default=-1.0) == -1.0


def test_alternate_yahoo_row_labels_are_recognised(monkeypatch):
    income = _frame(
        {
            "TotalRevenue": [120.0, 110.0, 100.0],
            "Net Income Common Stockholders": [12.0, 11.0, 10.0],
            "Normalized EBITDA": [30.0, 28.0, 25.0],
            "InterestExpense": [-3.0, -3.0, -3.0],  # sometimes reported as negative
        },
        Q3,
    )
    balance = _frame(
        {
            "Total Stockholder Equity": [200.0] * 3,
            "Total Current Assets": [90.0] * 3,
            "Total Current Liabilities": [60.0] * 3,
            "TotalDebt": [80.0] * 3,
        },
        Q3,
    )
    cashflow = _frame({"Cash Flow From Continuing Operating Activities": [20.0] * 3}, Q3)
    _use(monkeypatch, _ticker(income, balance, cashflow))

    latest = fetch_fundamentals("alt").quarters[-1]
    assert latest.revenue == 120.0 and latest.net_income == 12.0 and latest.ebitda == 30.0
    assert latest.interest_expense == 3.0
    assert (latest.total_equity, latest.current_assets, latest.current_liabilities) == (200.0, 90.0, 60.0)
    assert latest.total_debt == 80.0 and latest.operating_cash_flow == 20.0


def test_documented_fallbacks_for_missing_lines(monkeypatch):
    # no Gross Profit and no EBITDA rows: gross profit defaults to 40% of revenue,
    # EBITDA to operating income
    income = _frame({"Total Revenue": [100.0, 90.0], "Operating Income": [15.0, 12.0]}, Q3[:2])
    _use(monkeypatch, _ticker(income))
    latest = fetch_fundamentals("x").quarters[-1]
    assert latest.gross_profit == pytest.approx(40.0)
    assert latest.ebitda == 15.0


def test_only_the_eight_newest_quarters_are_kept_with_iso_dates(monkeypatch):
    dates = [str(d.date()) for d in pd.date_range("2023-03-31", periods=10, freq="QE")][::-1]  # newest first
    income = _frame({"Total Revenue": [float(100 + i) for i in range(10)][::-1]}, dates)
    _use(monkeypatch, _ticker(income))

    quarters = fetch_fundamentals("x").quarters
    assert len(quarters) == fetch_module.MAX_QUARTERS == 8
    assert [q.period for q in quarters] == sorted(dates)[-8:]  # oldest two dropped, oldest first
    assert quarters[-1].period == "2025-06-30"  # plain YYYY-MM-DD (the backtest export relies on it)


def test_quarters_without_revenue_are_skipped(monkeypatch):
    income = _frame({"Total Revenue": [130.0, float("nan"), 0.0, 100.0]}, ["2025-06-30", *Q3[1:], "2024-09-30"])
    _use(monkeypatch, _ticker(income))
    assert [q.revenue for q in fetch_fundamentals("x").quarters] == [100.0, 130.0]


def test_too_little_history_raises(monkeypatch):
    income = _frame({"Total Revenue": [100.0, 0.0, float("nan")]}, Q3)  # only one usable quarter
    _use(monkeypatch, _ticker(income))
    with pytest.raises(DataUnavailableError, match="insufficient quarterly history"):
        fetch_fundamentals("x")


def test_missing_balance_sheet_and_cash_flow_frames_do_not_crash(monkeypatch):
    income = _frame({"Total Revenue": [120.0, 100.0], "Net Income": [12.0, 10.0]}, Q3[:2])
    for empty in (None, pd.DataFrame()):

        class NoStatements(_ticker(income)):
            def __init__(self, symbol):
                super().__init__(symbol)
                self.quarterly_balance_sheet = empty
                self.quarterly_cashflow = empty

        _use(monkeypatch, NoStatements)
        snapshot = fetch_fundamentals("x")
        assert [q.revenue for q in snapshot.quarters] == [100.0, 120.0]
        assert snapshot.quarters[-1].net_income == 12.0


def test_info_failure_still_returns_the_statements(monkeypatch):
    income = _frame({"Total Revenue": [120.0, 100.0]}, Q3[:2])
    _use(monkeypatch, _ticker(income, info_error=ConnectionError("quote endpoint down")))

    snapshot = fetch_fundamentals("abc")
    assert snapshot.company_name == "ABC"  # no name available -> the symbol
    assert snapshot.sector is None
    assert snapshot.valuation.trailing_pe is None and snapshot.reported.net_margin is None


def test_company_name_and_sector_fallbacks(monkeypatch):
    income = _frame({"Total Revenue": [120.0, 100.0]}, Q3[:2])
    _use(monkeypatch, _ticker(income, info={"shortName": "Short Co", "sector": ""}))
    snapshot = fetch_fundamentals("x")
    assert snapshot.company_name == "Short Co" and snapshot.sector is None


def test_annual_statements_are_optional(monkeypatch):
    income = _frame({"Total Revenue": [120.0, 100.0]}, Q3[:2])
    for annual in (None, pd.DataFrame(), RuntimeError("annual endpoint down")):
        _use(monkeypatch, _ticker(income, annual=annual))
        assert fetch_fundamentals("x").annual == []


def test_network_errors_are_wrapped_with_the_symbol(monkeypatch):
    def broken(symbol):
        raise ConnectionError("Yahoo said 429")

    _use(monkeypatch, broken)
    with pytest.raises(DataUnavailableError, match=r"failed for MSFT: Yahoo said 429") as exc:
        fetch_fundamentals("msft")
    assert isinstance(exc.value.__cause__, ConnectionError)
