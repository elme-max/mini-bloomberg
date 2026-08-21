import { NextResponse } from "next/server";
import { getEarnings } from "@/lib/yahoo";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  try {
    const earnings = await getEarnings(ticker.toUpperCase());
    return NextResponse.json(earnings);
  } catch {
    return NextResponse.json(
      { error: `Could not load earnings for ${ticker}` },
      { status: 404 }
    );
  }
}
