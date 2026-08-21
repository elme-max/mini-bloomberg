// Deterministic, per-symbol synthetic market data. Used only as a fallback
// when the live Yahoo Finance fetch fails (e.g. blocked network egress),
// so the dashboard stays fully functional and demo-able out of the box.
import type {
  EarningsData,
  EarningsQuarter,
  HistoryPoint,
  NewsItem,
  QuoteData,
  RatiosData,
} from "./types";

function seedFromSymbol(symbol: string): number {
  let h = 0;
  for (let i = 0; i < symbol.length; i++) h = (h * 31 + symbol.charCodeAt(i)) >>> 0;
  return h || 1;
}

function mulberry32(seed: number) {
  let a = seed;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const COMPANY_NAMES: Record<string, string> = {
  AAPL: "Apple Inc.",
  MSFT: "Microsoft Corporation",
  GOOGL: "Alphabet Inc.",
  AMZN: "Amazon.com, Inc.",
  NVDA: "NVIDIA Corporation",
  TSLA: "Tesla, Inc.",
  META: "Meta Platforms, Inc.",
  JPM: "JPMorgan Chase & Co.",
};

export function mockQuote(symbol: string): QuoteData {
  const rand = mulberry32(seedFromSymbol(symbol));
  const base = 40 + rand() * 400;
  const changePercent = (rand() - 0.5) * 6;
  const change = (base * changePercent) / 100;

  return {
    symbol,
    shortName: COMPANY_NAMES[symbol] ?? `${symbol} (demo)`,
    longName: COMPANY_NAMES[symbol] ?? `${symbol} (demo data)`,
    currency: "USD",
    regularMarketPrice: Number(base.toFixed(2)),
    regularMarketChange: Number(change.toFixed(2)),
    regularMarketChangePercent: Number(changePercent.toFixed(2)),
    regularMarketPreviousClose: Number((base - change).toFixed(2)),
    regularMarketOpen: Number((base - change * 0.6).toFixed(2)),
    regularMarketDayHigh: Number((base + Math.abs(change) * 0.8).toFixed(2)),
    regularMarketDayLow: Number((base - Math.abs(change) * 0.8).toFixed(2)),
    regularMarketVolume: Math.floor(1_000_000 + rand() * 40_000_000),
    marketCap: Math.floor(base * (1e8 + rand() * 2e10)),
    exchange: "Demo Exchange",
    marketState: "REGULAR",
  };
}

export function mockHistory(symbol: string, points = 130): HistoryPoint[] {
  const rand = mulberry32(seedFromSymbol(symbol));
  let price = 40 + rand() * 400;
  const out: HistoryPoint[] = [];
  const now = new Date();
  for (let i = points - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const drift = (rand() - 0.48) * 0.02;
    price = Math.max(1, price * (1 + drift));
    out.push({ date: d.toISOString().slice(0, 10), close: Number(price.toFixed(2)) });
  }
  return out;
}

export function mockRatios(symbol: string): RatiosData {
  const rand = mulberry32(seedFromSymbol(symbol) + 7);
  return {
    peRatioTrailing: Number((8 + rand() * 40).toFixed(2)),
    peRatioForward: Number((7 + rand() * 35).toFixed(2)),
    pegRatio: Number((0.5 + rand() * 2.5).toFixed(2)),
    priceToBook: Number((1 + rand() * 15).toFixed(2)),
    priceToSales: Number((0.5 + rand() * 12).toFixed(2)),
    dividendYield: Number((rand() * 0.035).toFixed(4)),
    profitMargin: Number((rand() * 0.35).toFixed(4)),
    operatingMargin: Number((rand() * 0.4).toFixed(4)),
    returnOnEquity: Number((rand() * 0.45).toFixed(4)),
    returnOnAssets: Number((rand() * 0.2).toFixed(4)),
    debtToEquity: Number((rand() * 200).toFixed(1)),
    currentRatio: Number((0.6 + rand() * 2.5).toFixed(2)),
    quickRatio: Number((0.4 + rand() * 2).toFixed(2)),
    earningsGrowth: Number(((rand() - 0.3) * 0.6).toFixed(4)),
    revenueGrowth: Number(((rand() - 0.2) * 0.5).toFixed(4)),
    beta: Number((0.5 + rand() * 1.5).toFixed(2)),
    fiftyTwoWeekHigh: Number((60 + rand() * 450).toFixed(2)),
    fiftyTwoWeekLow: Number((20 + rand() * 150).toFixed(2)),
    eps: Number((0.5 + rand() * 20).toFixed(2)),
    freeCashflow: Math.floor(rand() * 5e10),
    totalCash: Math.floor(rand() * 8e10),
    totalDebt: Math.floor(rand() * 6e10),
    recommendationKey: ["buy", "hold", "outperform"][Math.floor(rand() * 3)],
    targetMeanPrice: Number((50 + rand() * 400).toFixed(2)),
  };
}

export function mockNews(symbol: string): NewsItem[] {
  const templates = [
    `${symbol} shares move as investors weigh sector trends`,
    `Analysts revisit price targets for ${symbol}`,
    `What to know ahead of ${symbol}'s next earnings report`,
    `${symbol} in focus amid broader market volatility`,
    `Institutional investors adjust ${symbol} holdings`,
  ];
  return templates.map((title, i) => ({
    uuid: `demo-${symbol}-${i}`,
    title,
    publisher: "Demo Wire",
    link: "#",
    providerPublishTime: new Date(Date.now() - i * 6 * 3600 * 1000).toISOString(),
    thumbnail: null,
  }));
}

export function mockEarnings(symbol: string): EarningsData {
  const rand = mulberry32(seedFromSymbol(symbol) + 21);
  const history: EarningsQuarter[] = Array.from({ length: 4 }, (_, i) => {
    const est = Number((0.4 + rand() * 4).toFixed(2));
    const surprise = (rand() - 0.4) * 20;
    const actual = Number((est * (1 + surprise / 100)).toFixed(2));
    const d = new Date();
    d.setMonth(d.getMonth() - (4 - i) * 3);
    return {
      date: d.toISOString().slice(0, 10),
      epsActual: actual,
      epsEstimate: est,
      surprisePercent: Number(surprise.toFixed(1)),
    };
  });

  const nextDate = new Date();
  nextDate.setDate(nextDate.getDate() + 20 + Math.floor(rand() * 40));

  return {
    history,
    nextEarningsDate: nextDate.toISOString().slice(0, 10),
    revenueTTM: Math.floor(rand() * 4e11),
    earningsTTM: Math.floor(rand() * 8e10),
  };
}
