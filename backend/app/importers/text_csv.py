"""Plain CSV / text import: one draw per line."""

from __future__ import annotations

import re

from app.importers.common import (
    DateParseError,
    ParsedDraw,
    ParseResult,
    RejectedRow,
    find_date,
)
from app.validation import DrawValidationError, GameSpec, validate_draw

# Standalone integers only: "n1" in a header such as "date,n1,n2" is a label, not a number.
_INT = re.compile(r"(?<![A-Za-z0-9_])\d+(?![A-Za-z0-9_])")


def parse_text(text: str, spec: GameSpec, skip_leading: int = 0) -> ParseResult:
    """Parse draws from free-form text.

    Per line: detect a date, remove it, take every remaining integer, skip the first
    `skip_leading` of them (a draw-ID column), then take the next K. If the game has a
    bonus ball and exactly one integer is left after the K, it is the bonus. Any other
    leftover integers are ignored but counted in `warnings`.

    When `skip_leading >= 1` the first skipped integer is recorded as the draw number.
    Lines without any integer are headers. Rows are sorted oldest -> newest by date when
    every accepted row has a date, otherwise file order is kept.
    """
    if skip_leading < 0:
        raise ValueError("skip_leading must be >= 0")
    result = ParseResult()
    extra_rows = 0

    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip().lstrip("﻿")
        if not line:
            continue
        if not _INT.search(line):
            result.headers_skipped += 1
            continue
        try:
            date, rest = find_date(line)
        except DateParseError as exc:
            result.rejected.append(RejectedRow(line_no, raw, str(exc)))
            continue
        ints = [int(t) for t in _INT.findall(rest)]
        need = skip_leading + spec.k
        if len(ints) < need:
            result.rejected.append(
                RejectedRow(
                    line_no,
                    raw,
                    f"found {len(ints)} integers after removing the date; need "
                    f"{skip_leading} to skip + {spec.k} numbers",
                )
            )
            continue
        picked = ints[skip_leading:need]
        leftover = ints[need:]
        bonus: int | None = None
        if spec.has_bonus and len(leftover) == 1:
            bonus, leftover = leftover[0], []
        try:
            numbers, bonus = validate_draw(picked, spec, bonus)
        except DrawValidationError as exc:
            result.rejected.append(RejectedRow(line_no, raw, str(exc)))
            continue
        if leftover:
            extra_rows += 1
        result.draws.append(
            ParsedDraw(
                numbers=numbers,
                draw_date=date,
                draw_no=ints[0] if skip_leading >= 1 else None,
                bonus=bonus,
                line_no=line_no,
            )
        )

    if extra_rows:
        result.warnings.append(
            f"{extra_rows} row(s) had extra integers after the {spec.k} numbers; they were ignored"
        )

    if result.draws and all(d.draw_date is not None for d in result.draws):
        result.draws.sort(key=lambda d: (d.draw_date, d.draw_no if d.draw_no is not None else 0))
        result.ordering = "date"
    else:
        result.ordering = "file"
    return result
