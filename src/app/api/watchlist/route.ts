import { NextResponse } from "next/server";
import { getQuotes } from "@/lib/yahoo";
import { DEFAULT_WATCHLIST } from "@/lib/watchlist";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const symbolsParam = searchParams.get("symbols");
  const symbols = symbolsParam
    ? symbolsParam.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean)
    : [...DEFAULT_WATCHLIST];

  const quotes = await getQuotes(symbols);
  return NextResponse.json({ quotes });
}
