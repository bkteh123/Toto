// Mirrors the FastAPI response models (backend/app/schemas.py and app/api/*.py).

export type Method = "hot" | "cold" | "mixed" | "weighted" | "random";
export const METHODS: Method[] = ["hot", "cold", "mixed", "weighted", "random"];
export type NumberClass = "Hot" | "Cold" | "Neutral";
export type Period = "10" | "20" | "50" | "100" | "all";
export const PERIODS: Period[] = ["10", "20", "50", "100", "all"];

export interface Game {
  code: string;
  name: string;
  max_number: number;
  pick_count: number;
  has_bonus: boolean;
  bonus_max: number | null;
  ticket_price: string; // Decimal serialised as a string
  currency: string;
  is_default: boolean;
  is_preset: boolean;
}

export interface GameInput {
  code: string;
  name: string;
  max_number: number;
  pick_count: number;
  has_bonus: boolean;
  bonus_max: number | null;
  ticket_price: string;
  currency: string;
}

export interface Draw {
  draw_no: number | null;
  draw_date: string | null;
  numbers: number[];
  bonus: number | null;
  source: string;
}

export interface DrawPage {
  total: number;
  limit: number;
  offset: number;
  items: Draw[];
}

export interface MissingDraws {
  game: string;
  first_draw_no: number | null;
  last_draw_no: number | null;
  missing: number[];
}

export interface ImportResponse {
  log_id: number | null;
  status: "ok" | "conflict";
  format: "grid" | "text";
  added: number;
  skipped: number;
  rejected_count: number;
  rejected: { line_no: number; raw: string; reason: string }[];
  conflicts: Conflict[];
  missing_rows: { draw_no: number | null; draw_date: string | null }[];
  headers_skipped: number;
  warnings: string[];
  message: string;
}

export interface Conflict {
  draw_no: number | null;
  draw_date: string | null;
  existing_numbers: number[] | null;
  incoming_numbers: number[];
  reason: string;
}

export interface StoredConflict extends Conflict {
  id: number;
  source: string;
  status: string;
  import_log_id: number | null;
  created_at: string;
}

export type LogStatus = "running" | "ok" | "conflict" | "error" | "unreachable";

export interface CollectLog {
  id: number;
  game: string;
  kind: string;
  source: string;
  status: LogStatus;
  added: number;
  skipped: number;
  rejected: number;
  conflicts: number;
  started_at: string;
  finished_at: string | null;
  detail: Record<string, unknown> | null;
}

export interface NumberRow {
  number: number;
  appearances: number;
  frequency: number;
  gap: number;
  rank: number;
  hot: number;
  cold: number;
  combined: number;
  cls: NumberClass;
  counts: Record<"10" | "20" | "50" | "100" | "all", number>;
}

export interface Chip {
  number: number;
  appearances: number;
  gap: number;
}

export interface StatsResponse {
  game: string;
  n: number;
  k: number;
  draw_count: number;
  period: string;
  span: number;
  weights: number[];
  mix: number;
  expectation: {
    ticket_mean_matches: number;
    ticket_variance: number;
    p_at_least_3: number;
    appearances_in_period: number;
  };
  rows: NumberRow[];
  hottest_10: Chip[];
  coldest: Chip[];
  note: string;
}

export interface ScoreParams {
  w10: number;
  w20: number;
  w50: number;
  w100: number;
  mix: number; // percent
}

export interface GenerateResponse {
  game: string;
  method: Method;
  requested: number;
  combinations: number[][];
  shortfall: number;
  draw_count: number;
  note: string;
}

export interface BaoResponse {
  game: string;
  size: number;
  window: number;
  end_draw_no: number | null;
  end_draw_date: string | null;
  special_bao: boolean;
  numbers: number[];
  counts: Record<string, number>;
  cut_count: number;
  sure_in: number[];
  tied_alternatives: { number: number; appearances: number }[];
  unseen_filler: boolean;
  lines: number;
  ticket_price: number;
  currency: string;
  cost: number;
  jackpot_one_in: number;
  expected_hits: number;
  p_at_least_3_hits: number;
  later_draws: {
    draw_no: number | null;
    draw_date: string | null;
    numbers: number[];
    hits: number[];
    jackpot: boolean;
  }[];
  rule_check: {
    draws_tested: number;
    avg_hits: number;
    expected_hits: number;
    draws_with_3_plus: number;
    histogram: Record<string, number>;
  } | null;
  rule_note: string | null;
  note: string;
}

export interface BacktestMethodResult {
  method: Method;
  tickets: number;
  avg_matches: number;
  pct_vs_expected: number;
  rate_ge3: number;
  expected_ge3: number;
  z: number;
  p_value: number;
  p_by_draw: number | null;
  histogram: Record<string, number>;
  curve: number[];
  ticket_flag: boolean;
  beats_random: boolean;
  below_random: boolean;
}

export interface BacktestResult {
  n: number;
  k: number;
  warmup: number;
  tickets_per_draw: number;
  tested_draws: number;
  expected_mean: number;
  expected_variance: number;
  expected_ge3: number;
  methods: BacktestMethodResult[];
  verdict: {
    kind: "no_method" | "none_significant" | "some_significant";
    alpha: number;
    methods_compared: number;
    significant: Method[];
    below: Method[];
    ticket_only: Method[];
    text_en: string;
    text_zh: string;
  };
  labels: (number | null)[];
  history_draws: number;
}

export type BacktestStatus = "queued" | "running" | "done" | "error";

export interface BacktestJob {
  id: number;
  game: string;
  status: BacktestStatus;
  progress: number;
  params: Record<string, unknown>;
  result: BacktestResult | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  note: string;
}

export interface BacktestRequest {
  warmup: number;
  tickets: number;
  methods: Method[];
  seed?: number;
  w10: number;
  w20: number;
  w50: number;
  w100: number;
  mix: number;
}
