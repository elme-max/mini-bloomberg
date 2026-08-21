import { NextResponse } from "next/server";
import { getRatios } from "@/lib/yahoo";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  try {
    const ratios = await getRatios(ticker.toUpperCase());
    return NextResponse.json(ratios);
  } catch {
    return NextResponse.json(
      { error: `Could not load ratios for ${ticker}` },
      { status: 404 }
    );
  }
}
