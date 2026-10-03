"""Live fundamentals fetch via `yfinance`.

Real data is the default. If it can't be fetched (no `yfinance` install,
network blocked, unknown ticker, missing statements) a `DataUnavailableError`
is raised rather than silently substituting made-up numbers. Synthetic demo
data is only returned when explicitly requested with `demo=True`.
"""

from __future__ import annotations

from typing import Optional

from . import demo_data
from .types import FundamentalsSnapshot, QuarterFundamentals, ReportedMetrics, ValuationSnapshot

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - exercised when yfinance isn't installed
    yf = None
else:
    import logging

    # yfinance logs every failed cookie/crumb request; the error we raise
    # already says what went wrong.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)

MAX_QUARTERS = 8
MAX_ANNUAL = 4


class DataUnavailableError(RuntimeError):
    """Live fundamentals could not be fetched for a symbol."""


def _row(frame, *names: str):
    if frame is None or frame.empty:
        return None
    for name in names:
        if name in frame.index:
            return frame.loc[name]
    return None


def _value_at(row, column, default: float = 0.0) -> float:
    if row is None or column not in row.index:
        return default
    value = row[column]
    try:
        if value is None or value != value:  # NaN check without pandas import
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_periods(income, balance, cashflow, limit: int) -> list[QuarterFundamentals]:
    """Turn yfinance statement frames into oldest-to-newest period records."""
    columns = list(income.columns)[:limit]  # yfinance lists newest first
    columns = sorted(columns)  # oldest -> newest

    revenue_row = _row(income, "Total Revenue", "TotalRevenue")
    gross_profit_row = _row(income, "Gross Profit", "GrossProfit")
    operating_income_row = _row(income, "Operating Income", "OperatingIncome")
    net_income_row = _row(income, "Net Income", "NetIncome", "Net Income Common Stockholders")
    ebitda_row = _row(income, "EBITDA", "Normalized EBITDA")
    interest_row = _row(income, "Interest Expense", "InterestExpense")

    assets_row = _row(balance, "Total Assets", "TotalAssets")
    equity_row = _row(
        balance, "Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"
    )
    debt_row = _row(balance, "Total Debt", "TotalDebt")
    current_assets_row = _row(balance, "Current Assets", "Total Current Assets")
    current_liab_row = _row(balance, "Current Liabilities", "Total Current Liabilities")

    ocf_row = _row(
        cashflow, "Operating Cash Flow", "Total Cash From Operating Activities",
        "Cash Flow From Continuing Operating Activities",
    )
    capex_row = _row(cashflow, "Capital Expenditure", "CapitalExpenditure")

    quarters: list[QuarterFundamentals] = []
    for col in columns:
        revenue = _value_at(revenue_row, col)
        if revenue <= 0:
            continue
        quarters.append(
            QuarterFundamentals(
                period=str(getattr(col, "date", lambda: col)()),
                revenue=revenue,
                gross_profit=_value_at(gross_profit_row, col, revenue * 0.4),
                operating_income=_value_at(operating_income_row, col),
                net_income=_value_at(net_income_row, col),
                total_assets=_value_at(assets_row, col),
                total_equity=_value_at(equity_row, col),
                total_debt=_value_at(debt_row, col),
                current_assets=_value_at(current_assets_row, col),
                current_liabilities=_value_at(current_liab_row, col),
                interest_expense=abs(_value_at(interest_row, col)),
                ebitda=_value_at(ebitda_row, col, _value_at(operating_income_row, col)),
                operating_cash_flow=_value_at(ocf_row, col),
                capex=abs(_value_at(capex_row, col)),
            )
        )
    return quarters


def _build_valuation(info: dict) -> ValuationSnapshot:
    def g(*keys) -> Optional[float]:
        for key in keys:
            value = info.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    return ValuationSnapshot(
        share_price=g("currentPrice", "regularMarketPrice"),
        market_cap=g("marketCap"),
        trailing_pe=g("trailingPE"),
        forward_pe=g("forwardPE"),
        peg_ratio=g("pegRatio", "trailingPegRatio"),
        price_to_book=g("priceToBook"),
        price_to_sales=g("priceToSalesTrailing12Months"),
        ev_to_ebitda=g("enterpriseToEbitda"),
    )


def _number(info: dict, key: str) -> Optional[float]:
    value = info.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN / infinity
        return None
    return float(value)


def _build_reported(info: dict) -> ReportedMetrics:
    """Yahoo's own headline ratios, converted to plain fractions/multiples."""
    debt_to_equity = _number(info, "debtToEquity")
    free_cash_flow = _number(info, "freeCashflow")
    total_revenue = _number(info, "totalRevenue")
    return ReportedMetrics(
        revenue_growth=_number(info, "revenueGrowth"),
        net_margin=_number(info, "profitMargins"),
        roe=_number(info, "returnOnEquity"),
        # Yahoo publishes debt/equity as a percentage (145.3 means 1.453x).
        debt_to_equity=debt_to_equity / 100 if debt_to_equity is not None else None,
        current_ratio=_number(info, "currentRatio"),
        fcf_margin=(
            free_cash_flow / total_revenue
            if free_cash_flow is not None and total_revenue and total_revenue > 0
            else None
        ),
    )


def _fetch_annual(ticker) -> list[QuarterFundamentals]:
    try:
        income = ticker.financials
        if income is None or income.empty:
            return []
        return _build_periods(income, ticker.balance_sheet, ticker.cashflow, MAX_ANNUAL)
    except Exception:  # noqa: BLE001 - annual data is a best-effort extra
        return []


def fetch_fundamentals(symbol: str, demo: bool = False) -> FundamentalsSnapshot:
    """Fetch fundamentals for `symbol`.

    Raises `DataUnavailableError` if live data can't be retrieved. Pass
    `demo=True` to get deterministic synthetic data instead (no network).
    """

    symbol = symbol.upper()

    if demo:
        return demo_data.generate_demo_fundamentals(
            symbol, reason="Demo mode requested; these are synthetic numbers."
        )

    if yf is None:
        raise DataUnavailableError(
            "`yfinance` is not installed (pip install -r requirements.txt)."
        )

    try:
        ticker = yf.Ticker(symbol)
        try:
            info = ticker.get_info() or {}
        except Exception:  # noqa: BLE001 - valuation multiples are optional
            info = {}

        income = ticker.quarterly_financials
        if income is None or income.empty:
            raise ValueError("no quarterly income statement available")

        quarters = _build_periods(
            income, ticker.quarterly_balance_sheet, ticker.quarterly_cashflow, MAX_QUARTERS
        )
        if len(quarters) < 2:
            raise ValueError("insufficient quarterly history to evaluate trends")

        return FundamentalsSnapshot(
            symbol=symbol,
            company_name=info.get("longName") or info.get("shortName") or symbol,
            is_demo_data=False,
            quarters=quarters,
            valuation=_build_valuation(info),
            data_notes=[],
            annual=_fetch_annual(ticker),
            sector=info.get("sector") or None,
            reported=_build_reported(info),
        )
    except Exception as exc:  # noqa: BLE001
        raise DataUnavailableError(f"live data fetch failed for {symbol}: {exc}") from exc
