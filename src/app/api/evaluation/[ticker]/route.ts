import { NextResponse, type NextRequest } from "next/server";
import { EvaluationError, normalizeTicker, runEvaluation } from "@/lib/evaluation";

// The model fetches statements from Yahoo; a cold run can take several seconds.
export const maxDuration = 60;

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const symbol = normalizeTicker(ticker);
  if (!symbol) {
    return NextResponse.json(
      { error: `"${ticker.slice(0, 40)}" is not a valid ticker symbol` },
      { status: 400 }
    );
  }

  // Demo data is opt-in only (?demo=1); a failed live run is reported, never replaced.
  const demo = request.nextUrl.searchParams.get("demo") === "1";
  try {
    return NextResponse.json(await runEvaluation(symbol, { demo }));
  } catch (err) {
    const status = err instanceof EvaluationError ? err.status : 500;
    const message = err instanceof Error ? err.message : "Evaluation failed";
    return NextResponse.json({ error: message }, { status });
  }
}
