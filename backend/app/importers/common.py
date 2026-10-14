from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field


@dataclass
class ParsedDraw:
    numbers: list[int]
    draw_date: dt.date | None = None
    draw_no: int | None = None
    bonus: int | None = None
    line_no: int | None = None  # 1-based line (text) or sheet row (grid)


@dataclass
class RejectedRow:
    line_no: int
    raw: str
    reason: str


@dataclass
class MissingRow:
    """A draw row that exists in the source but has no numbers yet."""

    line_no: int
    draw_no: int | None
    draw_date: dt.date | None = None


@dataclass
class ParseResult:
    draws: list[ParsedDraw] = field(default_factory=list)  # oldest -> newest
    rejected: list[RejectedRow] = field(default_factory=list)
    missing: list[MissingRow] = field(default_factory=list)
    headers_skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    ordering: str = "date"  # 'date' | 'file'


_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_DMY = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)")


class DateParseError(ValueError):
    pass


def find_date(text: str) -> tuple[dt.date | None, str]:
    """Find the first dd/mm/yyyy or yyyy-mm-dd date in `text`.

    Returns (date, text-with-the-date-removed). An impossible date such as 31/02/2026
    raises DateParseError rather than being skipped, so the row is rejected, not mis-parsed.
    """
    iso, dmy = _ISO.search(text), _DMY.search(text)
    candidates = [m for m in (iso, dmy) if m]
    if not candidates:
        return None, text
    m = min(candidates, key=lambda x: x.start())
    try:
        if m is iso:
            d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        else:
            d = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError as exc:
        raise DateParseError(f"invalid date {m.group(0)!r}") from exc
    return d, text[: m.start()] + " " + text[m.end() :]
