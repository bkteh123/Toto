"""Persist parsed draws with the cross-check rule.

If any incoming draw disagrees with a stored draw (same draw number or same date but
different numbers/date), NOTHING from the batch is inserted. The disagreements are logged
to `draw_conflicts` for manual review. Draws that match a stored draw exactly are skipped.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importers.common import ParsedDraw, RejectedRow
from app.models import Draw, DrawConflict, Game, ImportLog
from app.validation import DrawValidationError, GameSpec, validate_draw


@dataclass
class ConflictInfo:
    draw_no: int | None
    draw_date: dt.date | None
    existing_numbers: list[int] | None
    incoming_numbers: list[int]
    reason: str


@dataclass
class StoreOutcome:
    status: str  # 'ok' | 'conflict'
    added: int = 0
    skipped: int = 0
    not_inserted: int = 0  # verify-only runs: new draws seen but deliberately not written
    rejected: list[RejectedRow] = field(default_factory=list)
    conflicts: list[ConflictInfo] = field(default_factory=list)
    log_id: int | None = None


def _key(d: ParsedDraw) -> str:
    return f"no {d.draw_no}" if d.draw_no is not None else f"date {d.draw_date}"


def store_draws(
    session: Session,
    game: Game,
    parsed: list[ParsedDraw],
    source: str,
    kind: str = "file",
    prior_rejected: list[RejectedRow] | None = None,
    detail: dict | None = None,
    log: ImportLog | None = None,
    insert_new: bool = True,
) -> StoreOutcome:
    """`log`: an existing ImportLog (e.g. status 'running') to finish instead of adding one.

    `insert_new=False` is verify-only: draws not yet stored are counted in `not_inserted`
    but never written; conflicts are still detected and logged.
    """
    spec = GameSpec.from_model(game)
    out = StoreOutcome(status="ok", rejected=list(prior_rejected or []))

    # 1. Re-validate everything against the game rules; invalid rows are rejected, not fixed.
    valid: list[ParsedDraw] = []
    for d in parsed:
        try:
            nums, bonus = validate_draw(d.numbers, spec, d.bonus)
        except DrawValidationError as exc:
            out.rejected.append(RejectedRow(d.line_no or 0, _key(d), str(exc)))
            continue
        if d.draw_no is None and d.draw_date is None:
            out.rejected.append(
                RejectedRow(d.line_no or 0, "numbers " + str(nums), "no draw number or date to identify the draw")
            )
            continue
        valid.append(ParsedDraw(nums, d.draw_date, d.draw_no, bonus, d.line_no))

    # 2. Compare against stored draws and within the batch.
    stored = session.scalars(select(Draw).where(Draw.game_id == game.id)).all()
    by_no = {s.draw_no: s for s in stored if s.draw_no is not None}
    by_date = {s.draw_date: s for s in stored if s.draw_date is not None}

    to_insert: list[ParsedDraw] = []
    seen_no: dict[int, ParsedDraw] = {}
    seen_date: dict[dt.date, ParsedDraw] = {}
    for d in valid:
        matches = []
        if d.draw_no is not None and d.draw_no in by_no:
            matches.append(by_no[d.draw_no])
        if d.draw_date is not None and d.draw_date in by_date and by_date[d.draw_date] not in matches:
            matches.append(by_date[d.draw_date])

        conflict_reason = None
        existing_numbers = None
        if len(matches) > 1:
            conflict_reason = "draw number and date point at two different stored draws"
            existing_numbers = matches[0].numbers
        elif matches:
            s = matches[0]
            existing_numbers = s.numbers
            if list(s.numbers) != d.numbers:
                conflict_reason = "numbers differ from the stored draw"
            elif d.bonus is not None and s.bonus is not None and d.bonus != s.bonus:
                conflict_reason = "bonus differs from the stored draw"
            elif (
                d.draw_no is not None and s.draw_no is not None and d.draw_no != s.draw_no
            ) or (
                d.draw_date is not None and s.draw_date is not None and d.draw_date != s.draw_date
            ):
                conflict_reason = "draw number/date differ from the stored draw"

        if conflict_reason is None:
            prev = (seen_no.get(d.draw_no) if d.draw_no is not None else None) or (
                seen_date.get(d.draw_date) if d.draw_date is not None else None
            )
            if prev is not None:
                if prev.numbers != d.numbers or (
                    prev.draw_no is not None and d.draw_no is not None and prev.draw_no != d.draw_no
                ):
                    conflict_reason = "same draw appears twice in this batch with different numbers or draw numbers"
                    existing_numbers = prev.numbers
                else:
                    out.skipped += 1
                    continue

        if conflict_reason is not None:
            out.conflicts.append(
                ConflictInfo(d.draw_no, d.draw_date, existing_numbers, d.numbers, conflict_reason)
            )
            continue
        if matches:  # identical to a stored draw
            out.skipped += 1
            continue
        to_insert.append(d)
        if d.draw_no is not None:
            seen_no[d.draw_no] = d
        if d.draw_date is not None:
            seen_date[d.draw_date] = d

    # 3. All-or-nothing on conflicts.
    if out.conflicts:
        out.status = "conflict"
        out.added = 0
    elif not insert_new:
        out.not_inserted = len(to_insert)
    else:
        for d in to_insert:
            session.add(
                Draw(
                    game_id=game.id,
                    draw_no=d.draw_no,
                    draw_date=d.draw_date,
                    numbers=d.numbers,
                    bonus=d.bonus,
                    source=source,
                )
            )
        out.added = len(to_insert)

    if log is None:
        log = ImportLog(game_id=game.id, kind=kind, source=source, status=out.status)
        session.add(log)
    log.status = out.status
    log.added = out.added
    log.skipped = out.skipped
    log.rejected = len(out.rejected)
    log.conflicts = len(out.conflicts)
    log.detail = detail
    log.finished_at = dt.datetime.now(dt.timezone.utc)
    session.flush()
    out.log_id = log.id
    for c in out.conflicts:
        session.add(
            DrawConflict(
                game_id=game.id,
                import_log_id=log.id,
                draw_no=c.draw_no,
                draw_date=c.draw_date,
                existing_numbers=c.existing_numbers,
                incoming_numbers=c.incoming_numbers,
                reason=c.reason,
                source=source,
            )
        )
    session.flush()
    return out


def missing_draw_numbers(session: Session, game: Game) -> list[int]:
    """Draw numbers absent between the lowest and highest stored draw number."""
    nos = sorted(
        n
        for (n,) in session.execute(
            select(Draw.draw_no).where(Draw.game_id == game.id, Draw.draw_no.is_not(None))
        )
    )
    if len(nos) < 2:
        return []
    have = set(nos)
    return [n for n in range(nos[0], nos[-1] + 1) if n not in have]
