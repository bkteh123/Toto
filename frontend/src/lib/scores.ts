import type { NumberClass, Period, StatsResponse } from "../api/types";
import { toCsv } from "./csv";

export interface ScoreRow {
  number: number;
  appearances: number;
  frequency: number;
  gap: number;
  rank: number;
  hot: number;
  cold: number;
  combined: number;
  cls: NumberClass;
}

export type SortKey = keyof ScoreRow;

/** Draws a period actually covers: min(period, drawCount). */
export function spanFor(period: Period, drawCount: number): number {
  return period === "all" ? drawCount : Math.min(Number(period), drawCount);
}

/** Expected appearances of any one number in `span` draws: span * K / N. */
export function expectedAppearances(span: number, k: number, n: number): number {
  return n > 0 ? (span * k) / n : 0;
}

/** Table rows for a period, taken from the per-window counts the API already returns. */
export function rowsForPeriod(stats: StatsResponse, period: Period): ScoreRow[] {
  const span = spanFor(period, stats.draw_count);
  return stats.rows.map((r) => ({
    number: r.number,
    appearances: r.counts[period],
    frequency: span > 0 ? r.counts[period] / span : 0,
    gap: r.gap,
    rank: r.rank,
    hot: r.hot,
    cold: r.cold,
    combined: r.combined,
    cls: r.cls,
  }));
}

const CLASS_ORDER: Record<NumberClass, number> = { Hot: 0, Neutral: 1, Cold: 2 };

/** Stable sort; ties always fall back to the lower number so the order never jumps. */
export function sortRows(rows: ScoreRow[], key: SortKey, dir: 1 | -1): ScoreRow[] {
  return [...rows].sort((a, b) => {
    const x = key === "cls" ? CLASS_ORDER[a.cls] : a[key];
    const y = key === "cls" ? CLASS_ORDER[b.cls] : b[key];
    if (x < y) return -dir;
    if (x > y) return dir;
    return a.number - b.number;
  });
}

/** First click on a column: ascending for "smaller is better" columns, descending otherwise. */
export function defaultSortDir(key: SortKey): 1 | -1 {
  return key === "number" || key === "rank" || key === "cls" ? 1 : -1;
}

export function scoresCsv(rows: ScoreRow[]): string {
  const sorted = [...rows].sort((a, b) => a.number - b.number);
  return toCsv([
    ["number", "appearances", "frequency", "draws_since", "alltime_rank", "hot", "cold", "combined", "class"],
    ...sorted.map((r) => [
      r.number,
      r.appearances,
      r.frequency.toFixed(4),
      r.gap,
      r.rank,
      r.hot.toFixed(4),
      r.cold.toFixed(4),
      r.combined.toFixed(4),
      r.cls,
    ]),
  ]);
}

/** The percentage each of the four window weights ends up with after normalisation. */
export function normalisedWeightPercents(w: number[]): number[] {
  const clean = w.map((x) => (Number.isFinite(x) && x > 0 ? x : 0));
  const sum = clean.reduce((a, b) => a + b, 0);
  return sum > 0 ? clean.map((x) => (x / sum) * 100) : clean.map(() => 0);
}
