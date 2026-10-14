export type Cell = string | number | boolean | null | undefined;

/** RFC 4180 style: quote a cell containing a comma, quote or line break. */
export function toCsv(rows: Cell[][]): string {
  const esc = (c: Cell): string => {
    const s = c === null || c === undefined ? "" : String(c);
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return rows.map((r) => r.map(esc).join(",")).join("\n");
}
