export interface QuoteData {
  symbol: string;
  shortName: string;
  longName?: string;
  currency?: string;
  regularMarketPrice: number;
  regularMarketChange: number;
  regularMarketChangePercent: number;
  regularMarketPreviousClose?: number;
  regularMarketOpen?: number;
  regularMarketDayHigh?: number;
  regularMarketDayLow?: number;
  regularMarketVolume?: number;
  marketCap?: number;
  exchange?: string;
  marketState?: string;
  source?: "live" | "demo";
}

export interface HistoryPoint {
  date: string;
  close: number;
  volume?: number;
}

export interface RatiosData {
  peRatioTrailing?: number | null;
  peRatioForward?: number | null;
  pegRatio?: number | null;
  priceToBook?: number | null;
  priceToSales?: number | null;
  dividendYield?: number | null;
  profitMargin?: number | null;
  operatingMargin?: number | null;
  returnOnEquity?: number | null;
  returnOnAssets?: number | null;
  debtToEquity?: number | null;
  currentRatio?: number | null;
  quickRatio?: number | null;
  earningsGrowth?: number | null;
  revenueGrowth?: number | null;
  beta?: number | null;
  fiftyTwoWeekHigh?: number | null;
  fiftyTwoWeekLow?: number | null;
  eps?: number | null;
  freeCashflow?: number | null;
  totalCash?: number | null;
  totalDebt?: number | null;
  recommendationKey?: string | null;
  targetMeanPrice?: number | null;
}

export interface NewsItem {
  uuid: string;
  title: string;
  publisher: string;
  link: string;
  providerPublishTime: string;
  thumbnail?: string | null;
}

export interface EarningsQuarter {
  date: string;
  epsActual?: number | null;
  epsEstimate?: number | null;
  surprisePercent?: number | null;
}

export interface EarningsData {
  history: EarningsQuarter[];
  nextEarningsDate?: string | null;
  revenueTTM?: number | null;
  earningsTTM?: number | null;
}

export interface EconomicSeriesPoint {
  date: string;
  value: number;
}

export interface EconomicIndicator {
  id: string;
  name: string;
  unit: string;
  latestValue: number;
  latestDate: string;
  previousValue?: number;
  change?: number;
  series: EconomicSeriesPoint[];
  source: "fred" | "mock";
}

export interface InsightsResponse {
  headlineSummary: string;
  insights: string[];
  outlookTone: "positive" | "neutral" | "cautious";
  generatedBy: "claude" | "heuristic";
  disclaimer: string;
}
