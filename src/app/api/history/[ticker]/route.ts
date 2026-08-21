import { NextResponse } from "next/server";
import { getHistory } from "@/lib/yahoo";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const { searchParams } = new URL(req.url);
  const range = (searchParams.get("range") as "1mo" | "6mo" | "1y" | "5y") || "6mo";

  try {
    const history = await getHistory(ticker.toUpperCase(), range);
    return NextResponse.json({ symbol: ticker.toUpperCase(), range, history });
  } catch {
    return NextResponse.json(
      { error: `Could not load history for ${ticker}` },
      { status: 404 }
    );
  }
}
