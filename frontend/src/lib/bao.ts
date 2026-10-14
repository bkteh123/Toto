import { toCsv } from "./csv";
import { pad } from "./format";

export const MAX_BAO_SIZE = 18;

/** Valid bao sizes for a K-from-N game: K-1 (the special "Bao 5" for a 6-number game) and K+1..18. */
export function baoSizes(n: number, k: number): number[] {
  const sizes: number[] = k - 1 >= 1 ? [k - 1] : [];
  for (let s = k + 1; s <= Math.min(MAX_BAO_SIZE, n); s++) sizes.push(s);
  return sizes;
}

export type RuleVerdict = "same" | "above" | "below";

/** The prototype's wording rule: within 15% of the random expectation counts as "same". */
export function ruleVerdict(avg: number, expected: number): RuleVerdict {
  if (Math.abs(avg - expected) < 0.15 * expected) return "same";
  return avg > expected ? "above" : "below";
}

export function combosCsv(combos: number[][], label: string): string {
  return toCsv(combos.map((c, i) => [i + 1, label, ...c.map(pad)]));
}

export function baoCsv(numbers: number[], counts: Record<string, number>): string {
  return toCsv([["number", "appearances"], ...numbers.map((n) => [n, counts[String(n)] ?? 0])]);
}
