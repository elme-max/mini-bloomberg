import { NextResponse } from "next/server";
import { getNews } from "@/lib/yahoo";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  try {
    const news = await getNews(ticker.toUpperCase());
    return NextResponse.json({ symbol: ticker.toUpperCase(), news });
  } catch {
    return NextResponse.json(
      { error: `Could not load news for ${ticker}` },
      { status: 404 }
    );
  }
}
