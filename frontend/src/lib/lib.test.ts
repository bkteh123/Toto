import { describe, expect, it } from "vitest";
import type { BacktestMethodResult, BacktestResult, StatsResponse } from "../api/types";
import { ApiError, errorMessage, exportUrl, filenameFromDisposition, qs } from "../api/client";
import { curveData, curveDomain, flagFor } from "./backtest";
import { toCsv } from "./csv";
import { fmtDate, fmtOneIn, fmtP, fmtPct, fmtSignedPct, pad } from "./format";
import {
  defaultSortDir,
  expectedAppearances,
  normalisedWeightPercents,
  rowsForPeriod,
  scoresCsv,
  sortRows,
  spanFor,
} from "./scores";

describe("format", () => {
  it("pads ball numbers to two digits", () => {
    expect(pad(3)).toBe("03");
    expect(pad(45)).toBe("45");
    expect(pad(100)).toBe("100");
  });
  it("formats percentages and signed percentages", () => {
    expect(fmtPct(0.0238, 2)).toBe("2.38%");
    expect(fmtSignedPct(4.24)).toBe("+4.2%");
    expect(fmtSignedPct(-3.26)).toBe("−3.3%");
    expect(fmtSignedPct(0)).toBe("+0.0%");
  });
  it("shows tiny p-values as a bound and null as a dash", () => {
    expect(fmtP(0.0004)).toBe("<0.001");
    expect(fmtP(0.0408)).toBe("0.041");
    expect(fmtP(null)).toBe("—");
    expect(fmtP(NaN)).toBe("—");
  });
  it("formats dates the way the source files do", () => {
    expect(fmtDate("2026-10-11")).toBe("11/10/2026");
    expect(fmtDate(null)).toBe("");
    expect(fmtDate("2026-10-11T03:00:00Z")).toBe("11/10/2026");
  });
  it("formats odds with a fractional part when small", () => {
    expect(fmtOneIn(290895)).toBe("1 / 290,895");
    expect(fmtOneIn(203626.5)).toBe("1 / 203,627");
    expect(fmtOneIn(12.5)).toBe("1 / 12.5");
  });
});

describe("csv", () => {
  it("quotes cells with commas, quotes and newlines", () => {
    expect(toCsv([["a", "b,c", 'd"e', "f\ng"]])).toBe('a,"b,c","d""e","f\ng"');
  });
  it("renders null and undefined as empty cells", () => {
    expect(toCsv([[1, null, undefined, 0]])).toBe("1,,,0");
  });
});

function stats(drawCount: number): StatsResponse {
  const mk = (n: number, c10: number, call: number, cls: "Hot" | "Cold" | "Neutral", gap: number, rank: number) => ({
    number: n,
    appearances: c10,
    frequency: 0,
    gap,
    rank,
    hot: n / 10,
    cold: 1 - n / 10,
    combined: 0.5,
    cls,
    counts: { "10": c10, "20": c10, "50": c10, "100": c10, all: call },
  });
  return {
    game: "g", n: 3, k: 1, draw_count: drawCount, period: "10", span: 0, weights: [], mix: 0.5,
    expectation: { ticket_mean_matches: 0, ticket_variance: 0, p_at_least_3: 0, appearances_in_period: 0 },
    rows: [mk(1, 2, 6, "Cold", 5, 2), mk(2, 5, 6, "Hot", 0, 1), mk(3, 2, 1, "Neutral", 3, 3)],
    hottest_10: [], coldest: [], note: "",
  };
}

describe("scores", () => {
  it("computes the span a period covers", () => {
    expect(spanFor("10", 122)).toBe(10);
    expect(spanFor("100", 40)).toBe(40);
    expect(spanFor("all", 122)).toBe(122);
  });
  it("computes the random expectation span*K/N", () => {
    expect(expectedAppearances(10, 6, 45)).toBeCloseTo(1.3333, 4);
    expect(expectedAppearances(122, 6, 45)).toBeCloseTo(16.2667, 4);
    expect(expectedAppearances(10, 6, 0)).toBe(0);
  });
  it("derives per-period rows from the counts the API returns", () => {
    const rows = rowsForPeriod(stats(10), "10");
    expect(rows.map((r) => r.appearances)).toEqual([2, 5, 2]);
    expect(rows[1].frequency).toBeCloseTo(0.5);
    const all = rowsForPeriod(stats(20), "all");
    expect(all.map((r) => r.appearances)).toEqual([6, 6, 1]);
    expect(all[0].frequency).toBeCloseTo(6 / 20);
    expect(rowsForPeriod(stats(0), "all")[0].frequency).toBe(0); // no division by zero
  });
  it("sorts with ties broken by number so the order is stable", () => {
    const rows = rowsForPeriod(stats(10), "10");
    expect(sortRows(rows, "appearances", -1).map((r) => r.number)).toEqual([2, 1, 3]);
    expect(sortRows(rows, "appearances", 1).map((r) => r.number)).toEqual([1, 3, 2]);
    expect(sortRows(rows, "number", -1).map((r) => r.number)).toEqual([3, 2, 1]);
    expect(sortRows(rows, "cls", 1).map((r) => r.cls)).toEqual(["Hot", "Neutral", "Cold"]);
    expect(rows.map((r) => r.number)).toEqual([1, 2, 3]); // input is not mutated
  });
  it("starts 'smaller is better' columns ascending", () => {
    expect(defaultSortDir("number")).toBe(1);
    expect(defaultSortDir("rank")).toBe(1);
    expect(defaultSortDir("hot")).toBe(-1);
    expect(defaultSortDir("gap")).toBe(-1);
  });
  it("builds the CSV the prototype copied", () => {
    const csv = scoresCsv(rowsForPeriod(stats(10), "10"));
    const lines = csv.split("\n");
    expect(lines[0]).toBe("number,appearances,frequency,draws_since,alltime_rank,hot,cold,combined,class");
    expect(lines[1]).toBe("1,2,0.2000,5,2,0.1000,0.9000,0.5000,Cold");
    expect(lines).toHaveLength(4);
  });
  it("normalises the four window weights to percentages", () => {
    expect(normalisedWeightPercents([40, 25, 20, 15])).toEqual([40, 25, 20, 15]);
    expect(normalisedWeightPercents([1, 1, 1, 1])).toEqual([25, 25, 25, 25]);
    expect(normalisedWeightPercents([0, 0, 0, 0])).toEqual([0, 0, 0, 0]);
    expect(normalisedWeightPercents([2, -5, NaN, 2])).toEqual([50, 0, 0, 50]);
  });
});

describe("backtest helpers", () => {
  const method = (m: Partial<BacktestMethodResult>): BacktestMethodResult => ({
    method: "hot", tickets: 10, avg_matches: 0.8, pct_vs_expected: 0, rate_ge3: 0, expected_ge3: 0.02, z: 0,
    p_value: 0.5, p_by_draw: 0.5, histogram: {}, curve: [], ticket_flag: false, beats_random: false,
    below_random: false, ...m,
  });
  it("classifies the flag shown next to a method", () => {
    expect(flagFor(method({ beats_random: true, ticket_flag: true }))).toBe("beats");
    expect(flagFor(method({ ticket_flag: true }))).toBe("ticket_only");
    expect(flagFor(method({ below_random: true }))).toBe("below");
    expect(flagFor(method({}))).toBe("none");
  });
  const result = {
    n: 45, k: 6, warmup: 30, tickets_per_draw: 5, tested_draws: 3, expected_mean: 0.8, expected_variance: 0.6,
    expected_ge3: 0.0238,
    methods: [method({ method: "hot", curve: [0.7, 0.9, 0.85] }), method({ method: "random", curve: [0.8, 0.82, 0.78] })],
    verdict: {} as BacktestResult["verdict"], labels: [1483, 1484, null], history_draws: 33,
  } as BacktestResult;
  it("builds one chart row per tested draw, labelled by draw number", () => {
    const d = curveData(result);
    expect(d).toHaveLength(3);
    expect(d[0]).toMatchObject({ label: "1483", draw: 1483, hot: 0.7, random: 0.8 });
    expect(d[2].label).toBe("33"); // missing draw number falls back to the position
  });
  it("gives the y-axis room around the data and the expectation", () => {
    const [lo, hi] = curveDomain(result, 0);
    expect(lo).toBeLessThan(0.7);
    expect(hi).toBeGreaterThan(0.9);
    expect(lo).toBeGreaterThanOrEqual(0);
  });
});

describe("api client helpers", () => {
  it("extracts FastAPI error text", () => {
    expect(errorMessage({ detail: "no draws" }, "x")).toBe("no draws");
    expect(
      errorMessage({ detail: [{ loc: ["body", "count"], msg: "must be <= 50" }, { loc: ["body", "mix"], msg: "bad" }] }, "x"),
    ).toBe("count: must be <= 50; mix: bad");
    expect(errorMessage({}, "fallback")).toBe("fallback");
    expect(errorMessage(null, "fallback")).toBe("fallback");
  });
  it("builds query strings without empty values", () => {
    expect(qs({ a: 1, b: undefined, c: "x y", d: null })).toBe("?a=1&c=x+y");
    expect(qs({})).toBe("");
  });
  it("builds export URLs, carrying the on-screen parameters as a query", () => {
    expect(exportUrl("vn_mega_645", "draws", "xlsx")).toBe("/api/games/vn_mega_645/export/draws.xlsx");
    expect(exportUrl("vn_mega_645", "bao", "csv", { size: 8, window: 10, end_draw_no: null })).toBe(
      "/api/games/vn_mega_645/export/bao.csv?size=8&window=10",
    );
  });
  it("reads the download name from Content-Disposition", () => {
    expect(filenameFromDisposition(`attachment; filename="a-b.csv"; filename*=UTF-8''a-b.csv`, "x")).toBe("a-b.csv");
    expect(filenameFromDisposition(`attachment; filename*=UTF-8''%E5%BD%A9.csv`, "x")).toBe("彩.csv");
    expect(filenameFromDisposition(`attachment; filename=plain.xlsx`, "x")).toBe("plain.xlsx");
    expect(filenameFromDisposition(null, "fallback.csv")).toBe("fallback.csv");
  });
  it("ApiError carries the status", () => {
    const e = new ApiError(409, "busy");
    expect(e.status).toBe(409);
    expect(e.message).toBe("busy");
  });
});
