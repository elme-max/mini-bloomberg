"""Deterministic, per-symbol synthetic fundamentals.

Used only as a fallback when live data can't be fetched (no `yfinance`
install, blocked network egress, an unrecognized ticker, etc.), mirroring
the same demo-data pattern the Next.js app uses in `src/lib/mockMarket.ts`
so the model stays runnable and demo-able with zero setup.
"""

from __future__ import annotations

import random

from .types import FundamentalsSnapshot, QuarterFundamentals, ValuationSnapshot

NUM_QUARTERS = 8

_COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com, Inc.",
    "NVDA": "NVIDIA Corporation",
    "TSLA": "Tesla, Inc.",
    "META": "Meta Platforms, Inc.",
    "JPM": "JPMorgan Chase & Co.",
}


def _seed_from_symbol(symbol: str) -> int:
    h = 0
    for ch in symbol.upper():
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h or 1


def _quarter_label(index: int, quarters_ago: int) -> str:
    # index counts up from oldest (0) to newest; label purely for display.
    return f"Q{((index) % 4) + 1} (t-{quarters_ago})"


def generate_demo_fundamentals(symbol: str, reason: str | None = None) -> FundamentalsSnapshot:
    symbol = symbol.upper()
    rng = random.Random(_seed_from_symbol(symbol))

    base_revenue = rng.uniform(5e8, 6e10)
    quarterly_growth_bias = rng.uniform(-0.02, 0.07)  # per-quarter drift
    gross_margin = rng.uniform(0.30, 0.70)
    operating_margin = gross_margin * rng.uniform(0.35, 0.65)
    net_margin = operating_margin * rng.uniform(0.55, 0.90)
    equity_ratio = rng.uniform(0.25, 0.65)  # equity / assets
    debt_ratio = rng.uniform(0.10, 0.55)  # total debt / assets
    current_ratio_bias = rng.uniform(0.9, 2.5)
    capex_ratio = rng.uniform(0.03, 0.12)  # capex / revenue
    ocf_margin = net_margin + rng.uniform(0.02, 0.10)

    quarters: list[QuarterFundamentals] = []
    revenue = base_revenue
    for i in range(NUM_QUARTERS):
        noise = rng.uniform(-0.03, 0.03)
        if i > 0:
            revenue = revenue * (1 + quarterly_growth_bias + noise)
        gross_profit = revenue * max(0.05, gross_margin + rng.uniform(-0.02, 0.02))
        operating_income = revenue * max(-0.05, operating_margin + rng.uniform(-0.02, 0.02))
        net_income = revenue * (net_margin + rng.uniform(-0.02, 0.02))
        total_assets = revenue * rng.uniform(1.2, 2.5)
        total_equity = total_assets * equity_ratio
        total_debt = total_assets * debt_ratio
        current_assets = total_assets * rng.uniform(0.25, 0.5)
        current_liabilities = current_assets / current_ratio_bias
        interest_expense = total_debt * rng.uniform(0.02, 0.06)
        ebitda = operating_income + revenue * rng.uniform(0.02, 0.06)
        operating_cash_flow = revenue * (ocf_margin + rng.uniform(-0.02, 0.02))
        capex = revenue * capex_ratio

        quarters.append(
            QuarterFundamentals(
                period=_quarter_label(i, NUM_QUARTERS - 1 - i),
                revenue=revenue,
                gross_profit=gross_profit,
                operating_income=operating_income,
                net_income=net_income,
                total_assets=total_assets,
                total_equity=total_equity,
                total_debt=total_debt,
                current_assets=current_assets,
                current_liabilities=current_liabilities,
                interest_expense=interest_expense,
                ebitda=ebitda,
                operating_cash_flow=operating_cash_flow,
                capex=capex,
            )
        )

    share_price = rng.uniform(10, 500)
    eps = quarters[-1].net_income / rng.uniform(1e8, 5e9)
    trailing_pe = share_price / eps if eps > 0 else None
    valuation = ValuationSnapshot(
        share_price=share_price,
        market_cap=share_price * rng.uniform(1e8, 2e10),
        trailing_pe=trailing_pe,
        forward_pe=trailing_pe * rng.uniform(0.75, 1.1) if trailing_pe else None,
        peg_ratio=rng.uniform(0.6, 3.5),
        price_to_book=rng.uniform(0.8, 12),
        price_to_sales=rng.uniform(0.5, 15),
        ev_to_ebitda=rng.uniform(4, 30),
    )

    notes = [reason or "Live data unavailable; showing deterministic demo data."]
    return FundamentalsSnapshot(
        symbol=symbol,
        company_name=_COMPANY_NAMES.get(symbol, f"{symbol} (Demo Data)"),
        is_demo_data=True,
        quarters=quarters,
        valuation=valuation,
        data_notes=notes,
    )
