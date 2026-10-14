"""Walk-forward backtest (section 6).

For every draw t >= warm-up the scores are computed from draws[0:t] ONLY, tickets are
generated per method, and the matches against draw t are counted. A draw can therefore
never influence its own prediction.

Statistics per method, against the exact hypergeometric expectation for a random ticket:

  avg matches        mean matches over all tickets
  % vs expected      (avg / mu - 1) * 100
  3+ rate            share of tickets with >= 3 matches, next to the exact expected rate
  z                  (avg - mu) / sqrt(sigma^2 / n)       (the spec's ticket-level test)
  p                  two-sided, exact normal tail
  p by draw          EXTRA: a t-test on the per-draw means. Tickets generated for the same
                     draw are correlated (a hot method buys overlapping tickets), which makes
                     the ticket-level p too optimistic: on 1,200 genuinely random histories it
                     flagged Hot in 3.7% and Cold in 3.2% of runs at a nominal 1%
                     (scripts/calibrate_backtest.py). The per-draw test stayed at 0.6-0.9%.

A method "beats random" only when BOTH tests give p < 0.01 and it is above expectation.
Passing the ticket-level test alone is reported separately and is not counted as a win.

Each method draws from its own RNG stream (seeded from `seed` and the method name), so
including or excluding a method never changes the tickets of another.

A result is a description of what happened on past draws. It is not evidence that a method
will do anything on future draws unless it repeats on draws not used to find it.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from app.analysis.expectation import match_mean, match_variance, prob_at_least
from app.analysis.generator import METHODS, make_combination
from app.analysis.scoring import DEFAULT_MIX, DEFAULT_WEIGHTS, compute_scores
from app.analysis.stattests import normal_two_sided_p, student_t_two_sided_p

ALPHA = 0.01

METHOD_NAMES_ZH = {"hot": "热号", "cold": "冷号", "mixed": "冷热混合", "weighted": "综合加权", "random": "随机"}
METHOD_NAMES_EN = {"hot": "Hot", "cold": "Cold", "mixed": "Mixed", "weighted": "Weighted", "random": "Random"}


def method_rng(seed: int, method: str) -> random.Random:
    """Deterministic stream per (seed, method). String seeding is stable across runs."""
    return random.Random(f"royal-yellow:{seed}:{method}")


@dataclass(frozen=True)
class MethodResult:
    method: str
    tickets: int
    avg_matches: float
    pct_vs_expected: float
    rate_ge3: float
    expected_ge3: float
    z: float
    p_value: float
    p_by_draw: float | None
    histogram: dict[int, int]  # matches -> number of tickets
    curve: list[float]  # cumulative average matches after each tested draw
    ticket_flag: bool  # ticket-level p < alpha and above expectation (the spec's test alone)
    beats_random: bool  # ticket-level AND per-draw p < alpha, above expectation (never for the control)
    below_random: bool  # ticket-level AND per-draw p < alpha, below expectation (never for the control)


@dataclass(frozen=True)
class Verdict:
    kind: str  # 'no_method' | 'none_significant' | 'some_significant'
    alpha: float
    methods_compared: int  # non-random methods in this run
    significant: list[str]
    below: list[str]
    ticket_only: list[str]  # pass the ticket-level test alone: not counted as beating random
    text_en: str
    text_zh: str


@dataclass(frozen=True)
class BacktestResult:
    n: int
    k: int
    warmup: int
    tickets_per_draw: int
    tested_draws: int
    expected_mean: float
    expected_variance: float
    expected_ge3: float
    methods: list[MethodResult]
    verdict: Verdict
    tickets_log: dict[str, list[list[list[int]]]] | None = field(default=None, compare=False)


def _names(ms: list[str], table: dict[str, str]) -> str:
    return ", ".join(table[m] for m in ms)


def _verdict(methods: list[MethodResult]) -> Verdict:
    compared = [m for m in methods if m.method != "random"]
    sig = [m.method for m in compared if m.beats_random]
    below = [m.method for m in compared if m.below_random]
    ticket_only = [m.method for m in compared if m.ticket_flag and not m.beats_random]
    count = len(compared)

    if not compared:
        en = "Only the random control was run, so there is nothing to compare it with."
        zh = "只运行了随机对照组，没有可比较的方法。"
        return Verdict("no_method", ALPHA, 0, [], [], [], en, zh)

    if not sig:
        en = (
            "No method beats random with p < 0.01. That is the expected result for a fair draw: "
            "how often a number appeared before says nothing about the next draw."
        )
        zh = "没有任何方法以统计上有意义的差距（p < 0.01）胜过随机。这是公平开奖的正常结果：过去的出现频率无法预测未来号码。"
        kind = "none_significant"
    else:
        en = (
            f"{_names(sig, METHOD_NAMES_EN)} scored above the random expectation with p < 0.01 in both "
            f"tests. Be careful: {count} method(s) were compared, so one of them crossing 0.01 by luck is "
            "not unlikely (multiple comparisons), and tickets made for the same draw are correlated. "
            "It only means something if it repeats on new draws that were not used to find it."
        )
        zh = (
            f"{_names(sig, METHOD_NAMES_ZH)}在两项检验中均以 p < 0.01 高于随机。请谨慎看待：本次共比较了 "
            f"{count} 种方法，其中一种碰巧越过 0.01 并不罕见（多重比较）；同一期的注之间有相关性。"
            "必须在没有用于发现它的新开奖中重复出现才可信。"
        )
        kind = "some_significant"
    if ticket_only:
        en += (
            f" {_names(ticket_only, METHOD_NAMES_EN)} passed only the ticket-level test (p < 0.01) and not "
            "the per-draw test. Tickets bought for the same draw are correlated, so the ticket-level "
            "p-value is too optimistic; this is not counted as beating random."
        )
        zh += (
            f"{_names(ticket_only, METHOD_NAMES_ZH)}只通过了按注检验（p < 0.01），没有通过按期检验。"
            "同一期的注之间有相关性，按注的 p 值过于乐观，因此不算胜过随机。"
        )
    if below:
        en += (
            f" {_names(below, METHOD_NAMES_EN)} scored below random with p < 0.01 in both tests; that is "
            "no more usable than a high score and is just as likely to be chance."
        )
        zh += f"{_names(below, METHOD_NAMES_ZH)}在两项检验中均以 p < 0.01 低于随机，这同样不是可用的信号，同样很可能只是巧合。"
    return Verdict(kind, ALPHA, count, sig, below, ticket_only, en, zh)


def run_backtest(
    draws: Sequence[Sequence[int]],
    n: int,
    k: int,
    *,
    warmup: int = 30,
    tickets: int = 5,
    methods: Sequence[str] = METHODS,
    weights: Sequence[float] = DEFAULT_WEIGHTS,
    mix: float = DEFAULT_MIX,
    seed: int = 0,
    progress: Callable[[float], None] | None = None,
    record_tickets: bool = False,
) -> BacktestResult:
    """Walk forward over `draws` (oldest first). See the module docstring."""
    ms = list(dict.fromkeys(methods))  # de-duplicate, keep order
    bad = [m for m in ms if m not in METHODS]
    if bad or not ms:
        raise ValueError(f"methods must be a non-empty subset of {METHODS} (got {list(methods)!r})")
    if not (isinstance(warmup, int) and warmup >= 1):
        raise ValueError("warmup must be an integer >= 1")
    if not (isinstance(tickets, int) and 1 <= tickets <= 50):
        raise ValueError("tickets per draw must be an integer between 1 and 50")
    total = len(draws)
    tested = total - warmup
    if tested < 1:
        raise ValueError(f"need more than {warmup} draws to test anything (have {total})")

    mu = match_mean(n, k)
    var = match_variance(n, k)
    exp_ge3 = prob_at_least(n, k, 3)

    rngs = {m: method_rng(seed, m) for m in ms}
    hist = {m: Counter() for m in ms}
    hits_total = {m: 0 for m in ms}
    ge3 = {m: 0 for m in ms}
    curves: dict[str, list[float]] = {m: [] for m in ms}
    per_draw_means: dict[str, list[float]] = {m: [] for m in ms}
    log: dict[str, list[list[list[int]]]] | None = {m: [] for m in ms} if record_tickets else None

    for step, t in enumerate(range(warmup, total)):
        history = draws[:t]  # strictly earlier draws: draw t itself is never visible
        table = compute_scores(history, n, weights, mix)
        actual = set(draws[t])
        for m in ms:
            combos = [make_combination(table, m, k, rngs[m]) for _ in range(tickets)]
            if log is not None:
                log[m].append(combos)
            draw_hits = 0
            for c in combos:
                h = sum(1 for x in c if x in actual)
                hist[m][h] += 1
                draw_hits += h
                if h >= 3:
                    ge3[m] += 1
            hits_total[m] += draw_hits
            per_draw_means[m].append(draw_hits / tickets)
            curves[m].append(hits_total[m] / ((step + 1) * tickets))
        if progress is not None:
            progress((step + 1) / tested)

    results: list[MethodResult] = []
    for m in ms:
        count = tested * tickets
        avg = hits_total[m] / count
        z = (avg - mu) / math.sqrt(var / count)
        p = normal_two_sided_p(z)
        p_draw: float | None = None
        if tested >= 3:
            mean_d = sum(per_draw_means[m]) / tested
            ss = sum((x - mean_d) ** 2 for x in per_draw_means[m])
            if ss > 0:
                t_stat = (mean_d - mu) / math.sqrt(ss / (tested - 1) / tested)
                p_draw = student_t_two_sided_p(t_stat, tested - 1)
        control = m == "random"
        ticket_sig = p < ALPHA
        draw_sig = p_draw is not None and p_draw < ALPHA
        results.append(
            MethodResult(
                method=m,
                tickets=count,
                avg_matches=avg,
                pct_vs_expected=(avg / mu - 1.0) * 100.0,
                rate_ge3=ge3[m] / count,
                expected_ge3=exp_ge3,
                z=z,
                p_value=p,
                p_by_draw=p_draw,
                histogram={h: hist[m].get(h, 0) for h in range(k + 1)},
                curve=curves[m],
                ticket_flag=(not control) and ticket_sig and avg > mu,
                beats_random=(not control) and ticket_sig and draw_sig and avg > mu,
                below_random=(not control) and ticket_sig and draw_sig and avg < mu,
            )
        )
    return BacktestResult(
        n=n,
        k=k,
        warmup=warmup,
        tickets_per_draw=tickets,
        tested_draws=tested,
        expected_mean=mu,
        expected_variance=var,
        expected_ge3=exp_ge3,
        methods=results,
        verdict=_verdict(results),
        tickets_log=log,
    )
