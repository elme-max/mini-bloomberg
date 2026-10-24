// Runs the Python stock evolution model (python/stock_evolution_model) as a
// subprocess and returns its JSON report. Server-side only.
import { execFile } from "node:child_process";
import path from "node:path";
import type { EvaluationReport } from "./types";

// Yahoo-style symbols: AAPL, BRK-B, BF.B, ^GSPC, EURUSD=X. Must not start with
// "-" so it can never be read as a command-line option.
const TICKER_PATTERN = /^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$/;
const TIMEOUT_MS = 60_000;

export class EvaluationError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
  }
}

export function normalizeTicker(raw: string): string | null {
  const symbol = raw.trim().toUpperCase();
  return TICKER_PATTERN.test(symbol) ? symbol : null;
}

// The CLI reports a per-ticker failure on stderr as "<SYMBOL>: ERROR - <reason>".
function tickerError(stderr: string, symbol: string): string | null {
  const prefix = `${symbol}: ERROR - `;
  const line = stderr.split("\n").find((l) => l.startsWith(prefix));
  if (!line) return null;
  return line.slice(prefix.length).replace(`live data fetch failed for ${symbol}: `, "");
}

function lastLines(text: string, max = 300): string {
  const trimmed = text.trim();
  return trimmed.length > max ? `…${trimmed.slice(-max)}` : trimmed;
}

export function runEvaluation(symbol: string, { demo = false } = {}): Promise<EvaluationReport> {
  const pythonBin = process.env.PYTHON_BIN || "python3";
  const modelDir = process.env.STOCK_MODEL_DIR || path.join(process.cwd(), "python");
  // Arguments go straight to the process (no shell); "--" ends option parsing.
  const args = ["-m", "stock_evolution_model", "--json", ...(demo ? ["--demo"] : []), "--", symbol];

  return new Promise((resolve, reject) => {
    execFile(
      // The interpreter lives outside the project; without this hint Turbopack
      // traces the whole project because the command is only known at runtime.
      /* turbopackIgnore: true */ pythonBin,
      args,
      { cwd: modelDir, timeout: TIMEOUT_MS, maxBuffer: 5 * 1024 * 1024, windowsHide: true },
      (error, stdout, stderr) => {
        if (error) {
          if (error.code === "ENOENT") {
            return reject(
              new EvaluationError(
                `Python interpreter "${pythonBin}" was not found on the server (set PYTHON_BIN).`,
                500
              )
            );
          }
          if (error.killed) {
            return reject(new EvaluationError(`The evaluation model timed out for ${symbol}.`, 504));
          }
          const reason = tickerError(stderr, symbol);
          if (reason) {
            return reject(new EvaluationError(`Live data for ${symbol} is unavailable: ${reason}`, 503));
          }
          return reject(
            new EvaluationError(`The evaluation model failed to run. ${lastLines(stderr)}`.trim(), 500)
          );
        }
        try {
          const reports = JSON.parse(stdout) as EvaluationReport[];
          if (!Array.isArray(reports) || reports.length === 0) throw new Error("empty result");
          resolve(reports[0]);
        } catch {
          reject(new EvaluationError("The evaluation model returned unreadable output.", 500));
        }
      }
    );
  });
}
