import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Game, StatsResponse } from "./api/types";
import "./i18n";

const GAME: Game = {
  code: "vn_mega_645",
  name: "Vietlott Mega 6/45",
  max_number: 45,
  pick_count: 6,
  has_bonus: false,
  bonus_max: null,
  ticket_price: "10000.00",
  currency: "VND",
  is_default: true,
  is_preset: true,
};

const EMPTY_STATS: StatsResponse = {
  game: GAME.code,
  n: 45,
  k: 6,
  draw_count: 0,
  period: "all",
  span: 0,
  weights: [0.4, 0.25, 0.2, 0.15],
  mix: 0.5,
  expectation: { ticket_mean_matches: 0.8, ticket_variance: 0.6145, p_at_least_3: 0.023834, appearances_in_period: 0 },
  rows: [],
  hottest_10: [],
  coldest: [],
  note: "",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function fakeApi(url: string): Response {
  const path = url.replace(/^\/api/, "").split("?")[0];
  if (path === "/games") return json([GAME]);
  if (path === `/games/${GAME.code}/stats`) return json(EMPTY_STATS);
  if (path === `/games/${GAME.code}/draws`) return json({ total: 0, limit: 1, offset: 0, items: [] });
  if (path === `/games/${GAME.code}/draws/missing`)
    return json({ game: GAME.code, first_draw_no: null, last_draw_no: null, missing: [] });
  if (path === "/collect/logs" || path === `/games/${GAME.code}/conflicts`) return json([]);
  return json({ detail: `unexpected ${path}` }, 404);
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

describe("App", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => fakeApi(String(input))));
  });
  afterEach(() => vi.unstubAllGlobals());

  // Regression: the language effect used to depend on `t`, which changeLanguage re-creates,
  // so the app re-rendered forever ("Maximum update depth exceeded") and the page stayed blank.
  it("renders the dashboard in Chinese by default, then switches to English", async () => {
    const user = userEvent.setup();
    renderApp();

    expect(await screen.findByRole("heading", { level: 1, name: "Royal Yellow 分析器" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("zh-CN");
    // The disclaimer sits at the top of the page, before any score is shown.
    expect(document.querySelector(".disclaimer")).not.toBeNull();

    await user.click(screen.getByRole("button", { name: "English" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Royal Yellow Analyzer" })).toBeInTheDocument();
    await waitFor(() => expect(document.documentElement.lang).toBe("en"));
    expect(localStorage.getItem("ry_lang")).toBe("en");
  });

  it("says so, with a retry, when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    renderApp();
    expect(await screen.findByRole("button", { name: /重试|Retry/ })).toBeInTheDocument();
  });
});
