# mini-bloomberg

A personal investment dashboard: stock prices, key financial ratios,
economic indicators, company news and earnings — plus AI-generated,
plain-language headline summaries and investment insights.

## Features

- **Watchlist & stock pages** — live price, daily change, volume, market cap
  and an interactive price chart (1mo / 6mo / 1y / 5y) for any ticker.
- **Key financial ratios** — P/E, PEG, price/book, price/sales, dividend
  yield, margins, ROE/ROA, debt/equity, growth rates, beta, and more, each
  with a plain-language hint on hover.
- **Company news** — recent headlines per ticker, linked to the source.
- **Earnings** — last four quarters (EPS actual vs. estimate, surprise %),
  trailing revenue/net income, and the next expected report date.
- **Economic indicators** — inflation (CPI), unemployment, the Fed funds
  rate, real GDP, the 10-year Treasury yield, and consumer sentiment, sourced
  from FRED.
- **AI investment insights** — Claude summarizes recent headlines and
  translates the ratios/earnings/price action into a handful of short,
  jargon-light bullet points (never a buy/sell recommendation).

## Getting started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The app works out of
the box with **no API keys required** — stock and economic data come from
free/unofficial sources, with clearly-labeled synthetic "demo data" as a
fallback for any series that can't be reached (rate limits, blocked
datacenter IPs, etc. are common with the unofficial Yahoo Finance API).

## Optional environment variables

Set these in `.env.local` to enable live data / richer AI output:

| Variable            | Effect                                                                                   |
| -------------------- | ----------------------------------------------------------------------------------------- |
| `FRED_API_KEY`       | Live economic indicators from the [FRED API](https://fred.stlouisfed.org/docs/api/fred/) (free). Without it, the Economy page shows realistic demo series. |
| `ANTHROPIC_API_KEY`  | Uses Claude to generate the headline summary and investment insights. Without it, a deterministic rule-based summary is used instead. |

Stock prices, ratios, news and earnings use
[`yahoo-finance2`](https://github.com/gadicc/yahoo-finance2) and need no key,
but Yahoo's unofficial endpoints can be unreliable from some server/cloud
networks — when a live fetch fails, that ticker's data falls back to
deterministic per-symbol demo data and is labeled "demo" in the UI.

## Tech stack

- Next.js (App Router) + TypeScript + Tailwind CSS
- `yahoo-finance2` for market data, FRED for macro data, `@anthropic-ai/sdk` for insights
- `recharts` for charts, SWR for client-side data fetching

## Project structure

```
src/
  app/
    page.tsx               # dashboard home (watchlist + economy snapshot)
    stock/[ticker]/page.tsx  # per-stock detail page
    economy/page.tsx       # all economic indicators
    api/                   # REST endpoints backing the client components
  components/               # chart, ratio grid, news feed, insight panel, etc.
  lib/
    yahoo.ts                # market data with demo-data fallback
    fred.ts                 # economic indicators with demo-data fallback
    insights.ts              # Claude-powered / heuristic insight generation
    mockMarket.ts            # deterministic per-symbol demo data
```
