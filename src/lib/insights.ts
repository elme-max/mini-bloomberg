import Anthropic from "@anthropic-ai/sdk";
import type { EarningsData, InsightsResponse, NewsItem, QuoteData, RatiosData } from "./types";

const DISCLAIMER =
  "This is an automated, plain-language summary for educational purposes only — not financial advice.";

let client: Anthropic | null = null;
function getClient(): Anthropic | null {
  if (!process.env.ANTHROPIC_API_KEY) return null;
  if (!client) client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  return client;
}

interface InsightInputs {
  quote: QuoteData;
  ratios: RatiosData;
  news: NewsItem[];
  earnings: EarningsData;
}

export async function generateInsights({
  quote,
  ratios,
  news,
  earnings,
}: InsightInputs): Promise<InsightsResponse> {
  const anthropic = getClient();
  if (!anthropic) return heuristicInsights({ quote, ratios, news, earnings });

  const prompt = buildPrompt({ quote, ratios, news, earnings });

  try {
    const message = await anthropic.messages.create({
      model: "claude-sonnet-4-5",
      max_tokens: 700,
      messages: [{ role: "user", content: prompt }],
    });

    const text = message.content
      .filter((b) => b.type === "text")
      .map((b) => (b as { text: string }).text)
      .join("\n");

    return parseModelOutput(text);
  } catch (err) {
    console.error("Claude insight generation failed, falling back:", err);
    return heuristicInsights({ quote, ratios, news, earnings });
  }
}

function buildPrompt({ quote, ratios, news, earnings }: InsightInputs): string {
  const headlines = news.slice(0, 6).map((n) => `- ${n.title} (${n.publisher})`).join("\n");
  const lastEarnings = earnings.history.slice(-4);

  return `You are a financial explainer for a retail-investor dashboard called mini-bloomberg. \
Given the data below for ${quote.shortName} (${quote.symbol}), respond with STRICT JSON only, no markdown fences, matching this shape:
{
  "headlineSummary": "2-3 sentence plain-language summary of the recent news headlines",
  "insights": ["3 to 5 short bullet points, each in simple language a beginner investor understands, explaining what the ratios/earnings/price action mean"],
  "outlookTone": "positive" | "neutral" | "cautious"
}

Rules: no jargon without a quick explanation, no price predictions, no explicit buy/sell recommendations, keep each bullet under 30 words.

DATA:
Price: ${quote.regularMarketPrice} ${quote.currency ?? ""} (${quote.regularMarketChangePercent?.toFixed(2)}% today)
Market cap: ${quote.marketCap ?? "n/a"}
P/E (trailing): ${ratios.peRatioTrailing ?? "n/a"}
P/E (forward): ${ratios.peRatioForward ?? "n/a"}
Price/Book: ${ratios.priceToBook ?? "n/a"}
Dividend yield: ${ratios.dividendYield ?? "n/a"}
Profit margin: ${ratios.profitMargin ?? "n/a"}
Return on equity: ${ratios.returnOnEquity ?? "n/a"}
Debt/Equity: ${ratios.debtToEquity ?? "n/a"}
Revenue growth: ${ratios.revenueGrowth ?? "n/a"}
Earnings growth: ${ratios.earningsGrowth ?? "n/a"}
Analyst recommendation: ${ratios.recommendationKey ?? "n/a"}
Analyst target price: ${ratios.targetMeanPrice ?? "n/a"}
Next earnings date: ${earnings.nextEarningsDate ?? "n/a"}
Recent quarterly EPS vs estimate: ${JSON.stringify(lastEarnings)}

RECENT HEADLINES:
${headlines || "No recent headlines available."}`;
}

function parseModelOutput(text: string): InsightsResponse {
  const cleaned = text.trim().replace(/^```json/i, "").replace(/^```/, "").replace(/```$/, "");
  const parsed = JSON.parse(cleaned);
  return {
    headlineSummary: parsed.headlineSummary ?? "",
    insights: Array.isArray(parsed.insights) ? parsed.insights : [],
    outlookTone: ["positive", "neutral", "cautious"].includes(parsed.outlookTone)
      ? parsed.outlookTone
      : "neutral",
    generatedBy: "claude",
    disclaimer: DISCLAIMER,
  };
}

// Deterministic, rule-based fallback used when no ANTHROPIC_API_KEY is configured,
// so the dashboard remains fully functional out of the box.
function heuristicInsights({ quote, ratios, news, earnings }: InsightInputs): InsightsResponse {
  const insights: string[] = [];

  if (ratios.peRatioTrailing != null) {
    const level = ratios.peRatioTrailing > 30 ? "richly valued" : ratios.peRatioTrailing < 15 ? "cheaply valued" : "moderately valued";
    insights.push(
      `The P/E ratio (price relative to earnings) is ${ratios.peRatioTrailing.toFixed(1)}, which looks ${level} compared to a typical market average around 20.`
    );
  }

  if (ratios.returnOnEquity != null) {
    const pct = (ratios.returnOnEquity * 100).toFixed(1);
    insights.push(`Return on equity is ${pct}% — this measures how efficiently the company turns shareholder money into profit; higher is generally better.`);
  }

  if (ratios.debtToEquity != null) {
    const level = ratios.debtToEquity > 150 ? "carries a fair amount of debt" : "has a relatively conservative debt load";
    insights.push(`Debt-to-equity is ${ratios.debtToEquity.toFixed(1)}, meaning the company ${level} relative to its equity.`);
  }

  if (ratios.revenueGrowth != null) {
    const pct = (ratios.revenueGrowth * 100).toFixed(1);
    insights.push(`Revenue growth is ${pct}% — a rough gauge of whether the business is expanding or shrinking.`);
  }

  if (quote.regularMarketChangePercent != null) {
    const dir = quote.regularMarketChangePercent >= 0 ? "up" : "down";
    insights.push(`The stock is ${dir} ${Math.abs(quote.regularMarketChangePercent).toFixed(2)}% today, trading at ${quote.regularMarketPrice} ${quote.currency ?? ""}.`);
  }

  if (earnings.nextEarningsDate) {
    insights.push(`Next earnings report is expected around ${earnings.nextEarningsDate} — a key date that often moves the stock price.`);
  }

  const tone: InsightsResponse["outlookTone"] =
    (quote.regularMarketChangePercent ?? 0) > 1
      ? "positive"
      : (quote.regularMarketChangePercent ?? 0) < -1
      ? "cautious"
      : "neutral";

  const headlineSummary =
    news.length > 0
      ? `Recent coverage of ${quote.shortName} includes ${news.length} headlines from outlets like ${[...new Set(news.slice(0, 3).map((n) => n.publisher))].join(", ")}. Topics span company announcements and market commentary — see the news feed below for details.`
      : `No recent news headlines were found for ${quote.shortName}.`;

  return {
    headlineSummary,
    insights: insights.slice(0, 5),
    outlookTone: tone,
    generatedBy: "heuristic",
    disclaimer: DISCLAIMER,
  };
}
