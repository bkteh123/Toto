"""Collector interface: one subclass per result source."""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod

from app.importers.common import ParsedDraw


class CollectorError(Exception):
    """Base class; the message is shown to the user as-is."""


class SourceUnreachable(CollectorError):
    """Network failure or a non-200 answer after retries. The gap is left as it is."""


class PageLayoutError(CollectorError):
    """The page does not look like the layout this collector was written for.

    Fatal for the whole run: nothing is inserted and the run is reported, never guessed.
    """


class DrawNotPublished(CollectorError):
    """The source has no page for that date (it serves a different draw instead)."""


class Collector(ABC):
    game_code: str
    source_name: str
    #: how many draws one page lists (the requested draw plus those before it)
    draws_per_page: int
    #: weekday numbers (Mon=0) on which the game is drawn
    draw_weekdays: tuple[int, ...]
    #: local time the job should first run on a draw day, then hourly
    first_run_hour: int = 21

    @abstractmethod
    def page_url(self, date: dt.date) -> str: ...

    @abstractmethod
    def parse_page(self, html: str) -> list[ParsedDraw]:
        """Draws on a page, newest first. Strict: raise PageLayoutError on anything unexpected."""

    # ---- schedule helpers (shared) ----
    def is_draw_day(self, d: dt.date) -> bool:
        return d.weekday() in self.draw_weekdays

    def latest_scheduled_on_or_before(self, d: dt.date) -> dt.date:
        while not self.is_draw_day(d):
            d -= dt.timedelta(days=1)
        return d

    def previous_scheduled(self, d: dt.date) -> dt.date:
        return self.latest_scheduled_on_or_before(d - dt.timedelta(days=1))
