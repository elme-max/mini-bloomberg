"""Live fundamentals fetch via `yfinance`, with demo-data fallback.

Mirrors `src/lib/yahoo.ts`: try the live, unofficial Yahoo Finance data
first, and fall back to deterministic synthetic data (clearly labeled)
whenever the live fetch fails for any reason (no `yfinance` install,
network egress blocked, unknown ticker, missing statements, etc.).
"""

from __future__ import annotations

from typing import Optional

from . import demo_data
from .types import FundamentalsSnapshot, QuarterFundamentals, ValuationSnapshot

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - exercised when yfinance isn't installed
    yf = None

MAX_QUARTERS = 8


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


def _build_quarters(income, balance, cashflow) -> list[QuarterFundamentals]:
    columns = list(income.columns)[:MAX_QUARTERS]
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


def fetch_fundamentals(symbol: str) -> FundamentalsSnapshot:
    """Fetch fundamentals for `symbol`, falling back to demo data on any failure."""

    symbol = symbol.upper()

    if yf is None:
        return demo_data.generate_demo_fundamentals(
            symbol, reason="`yfinance` is not installed; showing demo data."
        )

    try:
        ticker = yf.Ticker(symbol)
        info = {}
        try:
            info = ticker.get_info() or {}
        except Exception:
            info = {}

        income = ticker.quarterly_financials
        balance = ticker.quarterly_balance_sheet
        cashflow = ticker.quarterly_cashflow

        if income is None or income.empty:
            raise ValueError("no quarterly income statement available")

        quarters = _build_quarters(income, balance, cashflow)
        if len(quarters) < 2:
            raise ValueError("insufficient quarterly history to evaluate trends")

        valuation = _build_valuation(info)
        company_name = info.get("longName") or info.get("shortName") or symbol

        return FundamentalsSnapshot(
            symbol=symbol,
            company_name=company_name,
            is_demo_data=False,
            quarters=quarters,
            valuation=valuation,
            data_notes=[],
        )
    except Exception as exc:  # noqa: BLE001 - any fetch failure falls back to demo data
        return demo_data.generate_demo_fundamentals(
            symbol, reason=f"Live data fetch failed ({exc}); showing demo data."
        )
