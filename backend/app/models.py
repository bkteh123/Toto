"""Database schema. Alembic migration 0001 mirrors this file; `alembic check` verifies it."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint("max_number BETWEEN 2 AND 500", name="ck_games_max_number"),
        CheckConstraint("pick_count BETWEEN 1 AND 20", name="ck_games_pick_count"),
        CheckConstraint("pick_count < max_number", name="ck_games_pick_lt_max"),
        CheckConstraint("ticket_price >= 0", name="ck_games_ticket_price"),
        CheckConstraint(
            "(has_bonus AND bonus_max BETWEEN 1 AND 500) OR (NOT has_bonus AND bonus_max IS NULL)",
            name="ck_games_bonus_consistent",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    max_number: Mapped[int] = mapped_column(Integer)  # N
    pick_count: Mapped[int] = mapped_column(Integer)  # K
    has_bonus: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    bonus_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ticket_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(8))
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_preset: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    draws: Mapped[list[Draw]] = relationship(back_populates="game", cascade="all, delete-orphan")


class Draw(Base):
    __tablename__ = "draws"
    __table_args__ = (
        UniqueConstraint("game_id", "draw_no", name="uq_draws_game_draw_no"),
        UniqueConstraint("game_id", "draw_date", name="uq_draws_game_draw_date"),
        CheckConstraint(
            "draw_no IS NOT NULL OR draw_date IS NOT NULL", name="ck_draws_has_identity"
        ),
        CheckConstraint("cardinality(numbers) BETWEEN 1 AND 20", name="ck_draws_numbers_len"),
        Index("ix_draws_game_date", "game_id", "draw_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    draw_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Nullable so a file without dates can still be analysed in file order (oldest -> newest).
    draw_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    numbers: Mapped[list[int]] = mapped_column(ARRAY(Integer))  # sorted ascending
    bonus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    game: Mapped[Game] = relationship(back_populates="draws")


class ImportLog(Base):
    """One row per import or collector run: what was added, skipped, rejected or in conflict."""

    __tablename__ = "import_logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','ok','conflict','error','unreachable')",
            name="ck_import_logs_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # 'file' | 'collector'
    source: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    added: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    skipped: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    rejected: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    conflicts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DrawConflict(Base):
    """Incoming draw that disagrees with a stored one. Held for manual review in the UI."""

    __tablename__ = "draw_conflicts"
    __table_args__ = (
        CheckConstraint("status IN ('open','resolved')", name="ck_draw_conflicts_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    import_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_logs.id", ondelete="SET NULL"), nullable=True
    )
    draw_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    draw_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    existing_numbers: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    incoming_numbers: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    reason: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'open'"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Backtest(Base):
    __tablename__ = "backtests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','done','error')", name="ck_backtests_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'queued'"))
    progress: Mapped[float] = mapped_column(Float, server_default=text("0"))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
