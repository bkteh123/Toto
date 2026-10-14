"""How often does the backtest flag a method on draws that are genuinely random?

A well-calibrated test at p < 0.01 should flag about 1% of runs. This reproduces the
check behind the "beats random needs BOTH tests" rule:

    python scripts/calibrate_backtest.py [runs] [draws]

Result recorded 2026-10-13 (1,200 random histories of 90 draws, warm-up 30, 5 tickets):

    method     ticket-level p<.01   per-draw p<.01
    hot              3.7%               0.7%
    cold             3.2%               0.6%
    mixed            1.2%               0.9%
    weighted         0.8%               0.6%
    random           1.0%               0.9%
"""

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.backtest import run_backtest  # noqa: E402

N, K = 45, 6
METHODS = ["hot", "cold", "mixed", "weighted", "random"]


def main(runs: int = 300, draws: int = 90) -> None:
    flagged_ticket = dict.fromkeys(METHODS, 0)
    flagged_draw = dict.fromkeys(METHODS, 0)
    t0 = time.time()
    for s in range(runs):
        rng = random.Random(500_000 + s)
        history = [sorted(rng.sample(range(1, N + 1), K)) for _ in range(draws)]
        r = run_backtest(history, N, K, warmup=30, tickets=5, methods=METHODS, seed=s)
        for m in r.methods:
            flagged_ticket[m.method] += m.p_value < 0.01
            flagged_draw[m.method] += (m.p_by_draw or 1.0) < 0.01
    print(f"{runs} random histories, {draws - 30} tested draws x 5 tickets, {time.time() - t0:.0f}s")
    print(f"nominal false-positive rate 1% = {runs * 0.01:.1f} runs")
    print(f"{'method':<10}{'ticket-level':>16}{'per-draw':>16}")
    for m in METHODS:
        print(f"{m:<10}{flagged_ticket[m]:>9} ({flagged_ticket[m] / runs:5.1%}){flagged_draw[m]:>9} ({flagged_draw[m] / runs:5.1%})")


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:3]))
