import type { EconomicIndicator, EconomicSeriesPoint } from "./types";

// Curated set of headline macro series from FRED (Federal Reserve Economic Data).
// https://fred.stlouisfed.org/docs/api/fred/
const SERIES = [
  { id: "CPIAUCSL", name: "Inflation (CPI, YoY)", unit: "%", asYoyPercent: true },
  { id: "UNRATE", name: "Unemployment Rate", unit: "%", asYoyPercent: false },
  { id: "FEDFUNDS", name: "Fed Funds Rate", unit: "%", asYoyPercent: false },
  { id: "GDPC1", name: "Real GDP", unit: "B$ (chained)", asYoyPercent: false },
  { id: "DGS10", name: "10-Year Treasury Yield", unit: "%", asYoyPercent: false },
  { id: "UMCSENT", name: "Consumer Sentiment", unit: "index", asYoyPercent: false },
] as const;

// Deterministic mock fallback so the dashboard is fully functional without an API key.
function mockSeries(seed: number, base: number, volatility: number, points = 24): EconomicSeriesPoint[] {
  const out: EconomicSeriesPoint[] = [];
  const now = new Date();
  let value = base;
  for (let i = points - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const wobble = Math.sin((i + seed) / 3) * volatility;
    value = base + wobble;
    out.push({ date: d.toISOString().slice(0, 10), value: Number(value.toFixed(2)) });
  }
  return out;
}

const MOCK_DEFAULTS: Record<string, { base: number; volatility: number; seed: number }> = {
  CPIAUCSL: { base: 3.1, volatility: 0.6, seed: 1 },
  UNRATE: { base: 4.1, volatility: 0.3, seed: 2 },
  FEDFUNDS: { base: 4.5, volatility: 0.4, seed: 3 },
  GDPC1: { base: 22000, volatility: 250, seed: 4 },
  DGS10: { base: 4.2, volatility: 0.35, seed: 5 },
  UMCSENT: { base: 68, volatility: 6, seed: 6 },
};

interface FredObservation {
  date: string;
  value: string;
}

async function fetchFredSeries(seriesId: string, apiKey: string): Promise<EconomicSeriesPoint[]> {
  const url = new URL("https://api.stlouisfed.org/fred/series/observations");
  url.searchParams.set("series_id", seriesId);
  url.searchParams.set("api_key", apiKey);
  url.searchParams.set("file_type", "json");
  url.searchParams.set("sort_order", "desc");
  url.searchParams.set("limit", "36");

  const res = await fetch(url.toString(), { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`FRED request failed: ${res.status}`);
  const data = await res.json();
  const obs: FredObservation[] = data.observations ?? [];

  return obs
    .filter((o) => o.value !== ".")
    .map((o) => ({ date: o.date, value: Number(o.value) }))
    .reverse();
}

function toYoyPercent(series: EconomicSeriesPoint[]): EconomicSeriesPoint[] {
  const out: EconomicSeriesPoint[] = [];
  for (let i = 12; i < series.length; i++) {
    const prior = series[i - 12].value;
    const current = series[i].value;
    if (prior === 0) continue;
    out.push({ date: series[i].date, value: Number((((current - prior) / prior) * 100).toFixed(2)) });
  }
  return out;
}

export async function getEconomicIndicators(): Promise<EconomicIndicator[]> {
  const apiKey = process.env.FRED_API_KEY;

  const indicators = await Promise.all(
    SERIES.map(async (def) => {
      try {
        if (!apiKey) throw new Error("no key");
        let series = await fetchFredSeries(def.id, apiKey);
        if (def.asYoyPercent) series = toYoyPercent(series);
        if (series.length === 0) throw new Error("empty series");

        const latest = series[series.length - 1];
        const previous = series[series.length - 2];
        return {
          id: def.id,
          name: def.name,
          unit: def.unit,
          latestValue: latest.value,
          latestDate: latest.date,
          previousValue: previous?.value,
          change: previous ? Number((latest.value - previous.value).toFixed(2)) : undefined,
          series: series.slice(-24),
          source: "fred" as const,
        };
      } catch {
        const m = MOCK_DEFAULTS[def.id];
        const series = mockSeries(m.seed, m.base, m.volatility);
        const latest = series[series.length - 1];
        const previous = series[series.length - 2];
        return {
          id: def.id,
          name: def.name,
          unit: def.unit,
          latestValue: latest.value,
          latestDate: latest.date,
          previousValue: previous?.value,
          change: previous ? Number((latest.value - previous.value).toFixed(2)) : undefined,
          series,
          source: "mock" as const,
        };
      }
    })
  );

  return indicators;
}
