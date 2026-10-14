/** Two-digit ball label: 3 -> "03". */
export const pad = (n: number): string => String(n).padStart(2, "0");

export const fmtInt = (n: number): string => Math.round(n).toLocaleString("en-US");

/** 0.0238 -> "2.38%". */
export const fmtPct = (ratio: number, digits = 1): string => `${(ratio * 100).toFixed(digits)}%`;

/** Signed percentage points already in percent: 4.2 -> "+4.2%". */
export const fmtSignedPct = (pct: number, digits = 1): string =>
  `${pct >= 0 ? "+" : "−"}${Math.abs(pct).toFixed(digits)}%`;

/** p-values: tiny ones are shown as a bound rather than as 0.000. */
export const fmtP = (p: number | null | undefined): string => {
  if (p === null || p === undefined || Number.isNaN(p)) return "—";
  return p < 0.001 ? "<0.001" : p.toFixed(3);
};

/** "2026-10-11" -> "11/10/2026" (the format used in the source files). */
export const fmtDate = (iso: string | null | undefined): string => {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
};

/** Odds of "1 in x"; x can be fractional (203,626.5) so keep it honest but readable. */
export const fmtOneIn = (x: number): string =>
  `1 / ${x >= 1000 ? Math.round(x).toLocaleString("en-US") : x.toFixed(1)}`;

export const fmtMoney = (value: number, currency: string): string =>
  `${Math.round(value).toLocaleString("en-US")} ${currency}`;
