import YahooFinance from "yahoo-finance2";
import type {
  EarningsData,
  EarningsQuarter,
  HistoryPoint,
  NewsItem,
  QuoteData,
  RatiosData,
} from "./types";
import { mockEarnings, mockHistory, mockNews, mockQuote, mockRatios } from "./mockMarket";

const yahooFinance = new YahooFinance({ suppressNotices: ["yahooSurvey"] });

// Yahoo's unofficial API occasionally fails (crumb/cookie issues, rate
// limiting, blocked datacenter IPs) depending on where this app is hosted.
// Every fetch below falls back to deterministic demo data so the dashboard
// stays usable and clearly labels itself when it isn't showing live data.
async function withFallback<T>(fetchLive: () => Promise<T>, fallback: () => T, label: string): Promise<T> {
  try {
    return await fetchLive();
  } catch (err) {
    console.warn(`[yahoo] live fetch failed for ${label}, using demo data:`, (err as Error).message);
    return fallback();
  }
}

async function fetchLiveQuote(symbol: string): Promise<QuoteData> {
  const q = await yahooFinance.quote(symbol);
  if (!q) throw new Error(`No quote found for ${symbol}`);
  return {
    symbol: q.symbol,
    shortName: q.shortName ?? q.symbol,
    longName: q.longName,
    currency: q.currency,
    regularMarketPrice: q.regularMarketPrice ?? 0,
    regularMarketChange: q.regularMarketChange ?? 0,
    regularMarketChangePercent: q.regularMarketChangePercent ?? 0,
    regularMarketPreviousClose: q.regularMarketPreviousClose,
    regularMarketOpen: q.regularMarketOpen,
    regularMarketDayHigh: q.regularMarketDayHigh,
    regularMarketDayLow: q.regularMarketDayLow,
    regularMarketVolume: q.regularMarketVolume,
    marketCap: q.marketCap,
    exchange: q.fullExchangeName,
    marketState: q.marketState,
    source: "live",
  };
}

export async function getQuote(symbol: string): Promise<QuoteData> {
  return withFallback(
    () => fetchLiveQuote(symbol),
    () => ({ ...mockQuote(symbol), source: "demo" as const }),
    `quote(${symbol})`
  );
}

export async function getQuotes(symbols: string[]): Promise<QuoteData[]> {
  const results = await Promise.all(symbols.map((s) => getQuote(s)));
  return results;
}

export async function getHistory(
  symbol: string,
  range: "1mo" | "6mo" | "1y" | "5y" = "6mo"
): Promise<HistoryPoint[]> {
  return withFallback(
    async () => {
      const period1 = new Date();
      const days: Record<string, number> = { "1mo": 31, "6mo": 186, "1y": 370, "5y": 1830 };
      period1.setDate(period1.getDate() - days[range]);

      const chart = await yahooFinance.chart(symbol, {
        period1,
        interval: range === "5y" ? "1wk" : "1d",
      });

      const points = chart.quotes
        .filter((c) => c.close != null)
        .map((c) => ({
          date: new Date(c.date).toISOString().slice(0, 10),
          close: Number(c.close?.toFixed(2)),
          volume: c.volume ?? undefined,
        }));
      if (points.length === 0) throw new Error("empty history");
      return points;
    },
    () => {
      const days: Record<string, number> = { "1mo": 22, "6mo": 130, "1y": 260, "5y": 260 };
      return mockHistory(symbol, days[range]);
    },
    `history(${symbol})`
  );
}

export async function getRatios(symbol: string): Promise<RatiosData> {
  return withFallback(
    async () => {
      const summary = await yahooFinance.quoteSummary(symbol, {
        modules: ["summaryDetail", "defaultKeyStatistics", "financialData"],
      });

      const sd = summary.summaryDetail;
      const ks = summary.defaultKeyStatistics;
      const fd = summary.financialData;

      return {
        peRatioTrailing: sd?.trailingPE ?? null,
        peRatioForward: sd?.forwardPE ?? ks?.forwardPE ?? null,
        pegRatio: ks?.pegRatio ?? null,
        priceToBook: ks?.priceToBook ?? null,
        priceToSales: sd?.priceToSalesTrailing12Months ?? null,
        dividendYield: sd?.dividendYield ?? null,
        profitMargin: fd?.profitMargins ?? null,
        operatingMargin: fd?.operatingMargins ?? null,
        returnOnEquity: fd?.returnOnEquity ?? null,
        returnOnAssets: fd?.returnOnAssets ?? null,
        debtToEquity: fd?.debtToEquity ?? null,
        currentRatio: fd?.currentRatio ?? null,
        quickRatio: fd?.quickRatio ?? null,
        earningsGrowth: fd?.earningsGrowth ?? null,
        revenueGrowth: fd?.revenueGrowth ?? null,
        beta: ks?.beta ?? null,
        fiftyTwoWeekHigh: sd?.fiftyTwoWeekHigh ?? null,
        fiftyTwoWeekLow: sd?.fiftyTwoWeekLow ?? null,
        eps: ks?.trailingEps ?? null,
        freeCashflow: fd?.freeCashflow ?? null,
        totalCash: fd?.totalCash ?? null,
        totalDebt: fd?.totalDebt ?? null,
        recommendationKey: fd?.recommendationKey ?? null,
        targetMeanPrice: fd?.targetMeanPrice ?? null,
      };
    },
    () => mockRatios(symbol),
    `ratios(${symbol})`
  );
}

export async function getNews(symbol: string, count = 8): Promise<NewsItem[]> {
  return withFallback(
    async () => {
      const result = await yahooFinance.search(symbol, {
        newsCount: count,
        quotesCount: 0,
      });

      const news = (result.news ?? []).slice(0, count).map((n) => ({
        uuid: n.uuid,
        title: n.title,
        publisher: n.publisher,
        link: n.link,
        providerPublishTime: new Date(n.providerPublishTime).toISOString(),
        thumbnail: n.thumbnail?.resolutions?.[0]?.url ?? null,
      }));
      if (news.length === 0) throw new Error("no news found");
      return news;
    },
    () => mockNews(symbol),
    `news(${symbol})`
  );
}

export async function getEarnings(symbol: string): Promise<EarningsData> {
  return withFallback(
    async () => {
      const summary = await yahooFinance.quoteSummary(symbol, {
        modules: ["earnings", "earningsHistory", "calendarEvents"],
      });

      const history: EarningsQuarter[] = (summary.earningsHistory?.history ?? []).map(
        (h) => ({
          date: h.quarter ? new Date(h.quarter).toISOString().slice(0, 10) : "",
          epsActual: h.epsActual ?? null,
          epsEstimate: h.epsEstimate ?? null,
          surprisePercent: h.surprisePercent ? h.surprisePercent * 100 : null,
        })
      );

      const nextDate = summary.calendarEvents?.earnings?.earningsDate?.[0];

      const financialsChart = summary.earnings?.financialsChart?.yearly ?? [];
      const lastYear = financialsChart[financialsChart.length - 1];

      if (history.length === 0) throw new Error("no earnings history");

      return {
        history,
        nextEarningsDate: nextDate ? new Date(nextDate).toISOString().slice(0, 10) : null,
        revenueTTM: lastYear?.revenue ?? null,
        earningsTTM: lastYear?.earnings ?? null,
      };
    },
    () => mockEarnings(symbol),
    `earnings(${symbol})`
  );
}
