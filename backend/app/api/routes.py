from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.importers.common import ParseResult
from app.importers.excel_grid import GridFormatError, parse_grid
from app.importers.service import missing_draw_numbers, store_draws
from app.importers.text_csv import parse_text
from app.models import Draw, Game
from app.validation import GameSpec

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _game(session: Session, code: str) -> Game:
    game = session.scalar(select(Game).where(Game.code == code))
    if game is None:
        raise HTTPException(404, f"unknown game {code!r}")
    return game


@router.get("/health")
def health(session: Session = Depends(get_session)):
    """Liveness + database reachability, used by the Docker healthcheck."""
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/games", response_model=list[schemas.GameOut])
def list_games(session: Session = Depends(get_session)):
    return session.scalars(select(Game).order_by(Game.is_default.desc(), Game.id)).all()


@router.post("/games", response_model=schemas.GameOut, status_code=201)
def create_game(body: schemas.GameIn, session: Session = Depends(get_session)):
    if session.scalar(select(Game.id).where(Game.code == body.code)) is not None:
        raise HTTPException(409, f"game {body.code!r} already exists")
    game = Game(**body.model_dump(), is_preset=False, is_default=False)
    session.add(game)
    session.commit()
    return game


@router.get("/games/{code}/draws", response_model=schemas.DrawPage)
def list_draws(
    code: str,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    game = _game(session, code)
    total = session.scalar(select(func.count()).select_from(Draw).where(Draw.game_id == game.id)) or 0
    # Newest first. Dateless draws are ordered by insertion (file order = oldest -> newest).
    rows = session.scalars(
        select(Draw)
        .where(Draw.game_id == game.id)
        .order_by(
            Draw.draw_date.desc().nulls_last(), Draw.draw_no.desc().nulls_last(), Draw.id.desc()
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return schemas.DrawPage(total=total, limit=limit, offset=offset, items=rows)


@router.get("/games/{code}/draws/missing", response_model=schemas.MissingDraws)
def missing_draws(code: str, session: Session = Depends(get_session)):
    game = _game(session, code)
    lo, hi = session.execute(
        select(func.min(Draw.draw_no), func.max(Draw.draw_no)).where(Draw.game_id == game.id)
    ).one()
    return schemas.MissingDraws(
        game=code,
        first_draw_no=lo,
        last_draw_no=hi,
        missing=missing_draw_numbers(session, game),
    )


@router.post("/games/{code}/draws/import", response_model=schemas.ImportResponse)
def import_draws(
    code: str,
    file: UploadFile = File(...),
    skip_leading: int = Form(0, ge=0, le=20),
    sheet: str | None = Form(None),
    session: Session = Depends(get_session),
):
    game = _game(session, code)
    spec = GameSpec.from_model(game)
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file larger than 10 MB")
    name = (file.filename or "upload").lower()

    parsed: ParseResult
    if name.endswith((".xlsx", ".xlsm")):
        fmt = "grid"
        try:
            parsed = parse_grid(raw, spec, sheet=sheet)
        except GridFormatError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:  # openpyxl raises a variety of types for corrupt files
            raise HTTPException(422, f"could not read workbook: {exc}") from exc
    else:
        fmt = "text"
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(422, "text file must be UTF-8") from None
        parsed = parse_text(text, spec, skip_leading=skip_leading)

    outcome = store_draws(
        session,
        game,
        parsed.draws,
        source=f"{fmt} import: {file.filename}",
        kind="file",
        prior_rejected=parsed.rejected,
        detail={
            "format": fmt,
            "filename": file.filename,
            "skip_leading": skip_leading,
            "missing_rows": [m.draw_no for m in parsed.missing],
            "ordering": parsed.ordering,
        },
    )
    session.commit()

    if outcome.status == "conflict":
        msg = (
            f"Nothing was imported: {len(outcome.conflicts)} draw(s) disagree with stored data. "
            "Review the conflicts."
        )
    else:
        msg = f"Added {outcome.added}, skipped {outcome.skipped} already stored."
    return schemas.ImportResponse(
        log_id=outcome.log_id,
        status=outcome.status,
        format=fmt,
        added=outcome.added,
        skipped=outcome.skipped,
        rejected_count=len(outcome.rejected),
        rejected=[
            schemas.RejectedOut(line_no=r.line_no, raw=r.raw[:200], reason=r.reason)
            for r in outcome.rejected[:100]
        ],
        conflicts=[
            schemas.ConflictOut(
                draw_no=c.draw_no,
                draw_date=c.draw_date,
                existing_numbers=c.existing_numbers,
                incoming_numbers=c.incoming_numbers,
                reason=c.reason,
            )
            for c in outcome.conflicts
        ],
        missing_rows=[schemas.MissingOut(draw_no=m.draw_no, draw_date=m.draw_date) for m in parsed.missing],
        headers_skipped=parsed.headers_skipped,
        warnings=parsed.warnings,
        message=msg,
    )
