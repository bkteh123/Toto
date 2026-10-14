import type { BacktestMethodResult, BacktestResult, Method } from "../api/types";

export type MethodFlag = "beats" | "ticket_only" | "below" | "none";

/** Colour per method; the colours are also used by the chart legend. */
export const METHOD_COLORS: Record<Method, string> = {
  hot: "#ff8a3d",
  cold: "#6fb7ff",
  mixed: "#c58cff",
  weighted: "#f2c230",
  random: "#f6ecd0",
};

export function flagFor(m: BacktestMethodResult): MethodFlag {
  if (m.beats_random) return "beats";
  if (m.below_random) return "below";
  if (m.ticket_flag) return "ticket_only";
  return "none";
}

export type CurvePoint = { label: string; draw: number | null } & Partial<Record<Method, number>>;

/** One row per tested draw with each method's cumulative average, for the line chart. */
export function curveData(result: BacktestResult): CurvePoint[] {
  const n = result.tested_draws;
  const out: CurvePoint[] = [];
  for (let i = 0; i < n; i++) {
    const draw = result.labels[i] ?? null;
    const pt: CurvePoint = { label: draw !== null ? String(draw) : String(result.warmup + i + 1), draw };
    for (const m of result.methods) pt[m.method] = m.curve[i];
    out.push(pt);
  }
  return out;
}

/** Y-axis range with a little headroom, ignoring the first few noisy points. */
export function curveDomain(result: BacktestResult, skip = 10): [number, number] {
  const vals: number[] = [result.expected_mean];
  for (const m of result.methods) vals.push(...m.curve.slice(Math.min(skip, Math.max(0, m.curve.length - 1))));
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = Math.max((hi - lo) * 0.1, 0.01);
  return [Math.max(0, Math.floor((lo - pad) * 100) / 100), Math.ceil((hi + pad) * 100) / 100];
}
