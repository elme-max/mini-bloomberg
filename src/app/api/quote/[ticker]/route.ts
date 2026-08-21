import { NextResponse } from "next/server";
import { getQuote } from "@/lib/yahoo";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  try {
    const quote = await getQuote(ticker.toUpperCase());
    return NextResponse.json(quote);
  } catch {
    return NextResponse.json(
      { error: `Could not load quote for ${ticker}` },
      { status: 404 }
    );
  }
}
