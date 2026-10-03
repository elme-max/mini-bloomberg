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
    assert snapshot.valuation.forward_pe == 18.0
    assert snapshot.valuation.ev_to_ebitda == 12.0


def test_live_path_scores_end_to_end(monkeypatch):
    monkeypatch.setattr(fetch_module, "yf", SimpleNamespace(Ticker=FakeTicker))

    report = StockEvolutionModel().analyze("fake")

    assert report.is_demo_data is False
    assert 0 <= report.overall_score <= 100
    growth = next(c for c in report.categories if c.name == "Revenue Growth")
    assert growth.metrics["growth_basis"] == "latest quarter vs same quarter last year"


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
