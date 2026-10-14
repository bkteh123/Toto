from app.collectors.base import Collector
from app.collectors.minhngoc import MinhNgocMega645

_COLLECTORS: dict[str, Collector] = {c.game_code: c for c in (MinhNgocMega645(),)}


def get_collector(game_code: str) -> Collector | None:
    """The collector for a game, or None when no source is wired up for it yet."""
    return _COLLECTORS.get(game_code)


def collector_game_codes() -> list[str]:
    return list(_COLLECTORS)
