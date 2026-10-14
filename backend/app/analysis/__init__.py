"""Pure statistics over a list of draws, oldest to newest.

Nothing in this package touches the database or the clock, so the backtest can call the
same functions on any prefix of the history without changing them.

Scores describe PAST behaviour. They are not probabilities of winning.
"""

from app.analysis.bao import BaoSet, RuleCheck, bao_set, jackpot_one_in, line_count, rule_check, valid_sizes
from app.analysis.expectation import (
    expected_appearances,
    hypergeom_pmf,
    match_distribution,
    match_mean,
    match_variance,
    prob_at_least,
)
from app.analysis.generator import (
    METHODS,
    GenerationResult,
    generate_combinations,
    make_combination,
    seeded_rng,
    system_rng,
)
from app.analysis.scoring import (
    DEFAULT_MIX,
    DEFAULT_WEIGHTS,
    PERIODS,
    NumberStat,
    ScoreTable,
    compute_scores,
    normalize_weights,
)

__all__ = [
    "DEFAULT_MIX",
    "DEFAULT_WEIGHTS",
    "METHODS",
    "PERIODS",
    "BaoSet",
    "GenerationResult",
    "NumberStat",
    "RuleCheck",
    "ScoreTable",
    "bao_set",
    "compute_scores",
    "expected_appearances",
    "generate_combinations",
    "hypergeom_pmf",
    "jackpot_one_in",
    "line_count",
    "make_combination",
    "match_distribution",
    "match_mean",
    "match_variance",
    "normalize_weights",
    "prob_at_least",
    "rule_check",
    "seeded_rng",
    "system_rng",
    "valid_sizes",
]
