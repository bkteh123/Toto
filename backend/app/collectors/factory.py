"""Construction helpers and the per-game run lock."""

from __future__ import annotations

import threading
from pathlib import Path

from app.collectors.fetcher import Fetcher
from app.config import get_settings

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def game_lock(game_code: str) -> threading.Lock:
    """One lock per game so the scheduler and a manual "Update now" never overlap."""
    with _locks_guard:
        return _locks.setdefault(game_code, threading.Lock())


def make_fetcher() -> Fetcher:
    s = get_settings()
    return Fetcher(
        user_agent=s.collector_user_agent,
        min_interval=s.collector_min_interval_seconds,
        cache_dir=Path(s.collector_cache_dir),
    )
