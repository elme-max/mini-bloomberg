import { NextResponse } from "next/server";
import { getEarnings, getNews, getQuote, getRatios } from "@/lib/yahoo";
import { generateInsights } from "@/lib/insights";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const symbol = ticker.toUpperCase();

  try {
    const [quote, ratios, news, earnings] = await Promise.all([
      getQuote(symbol),
      getRatios(symbol),
      getNews(symbol),
      getEarnings(symbol),
    ]);

    const insights = await generateInsights({ quote, ratios, news, earnings });
    return NextResponse.json(insights);
  } catch {
    return NextResponse.json(
      { error: `Could not generate insights for ${ticker}` },
      { status: 404 }
    );
  }
}
