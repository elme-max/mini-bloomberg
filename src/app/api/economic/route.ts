import { NextResponse } from "next/server";
import { getEconomicIndicators } from "@/lib/fred";

export async function GET() {
  const indicators = await getEconomicIndicators();
  return NextResponse.json({ indicators });
}
