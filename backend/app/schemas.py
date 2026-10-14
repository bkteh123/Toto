from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    max_number: int
    pick_count: int
    has_bonus: bool
    bonus_max: int | None
    ticket_price: Decimal
    currency: str
    is_default: bool
    is_preset: bool


class GameIn(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    max_number: int = Field(ge=2, le=500)
    pick_count: int = Field(ge=1, le=20)
    has_bonus: bool = False
    bonus_max: int | None = Field(default=None, ge=1, le=500)
    ticket_price: Decimal = Field(ge=0)
    currency: str = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _check(self) -> GameIn:
        if not re.fullmatch(r"[a-z0-9_]+", self.code):
            raise ValueError("code may contain only a-z, 0-9 and underscore")
        if self.pick_count >= self.max_number:
            raise ValueError("pick_count (K) must be smaller than max_number (N)")
        if self.has_bonus and self.bonus_max is None:
            raise ValueError("bonus_max is required when has_bonus is true")
        if not self.has_bonus and self.bonus_max is not None:
            raise ValueError("bonus_max must be empty when has_bonus is false")
        return self


class DrawOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    draw_no: int | None
    draw_date: dt.date | None
    numbers: list[int]
    bonus: int | None
    source: str


class DrawPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[DrawOut]


class RejectedOut(BaseModel):
    line_no: int
    raw: str
    reason: str


class ConflictOut(BaseModel):
    draw_no: int | None
    draw_date: dt.date | None
    existing_numbers: list[int] | None
    incoming_numbers: list[int]
    reason: str


class MissingOut(BaseModel):
    draw_no: int | None
    draw_date: dt.date | None


class ImportResponse(BaseModel):
    log_id: int | None
    status: str  # 'ok' | 'conflict'
    format: str  # 'grid' | 'text'
    added: int
    skipped: int
    rejected_count: int
    rejected: list[RejectedOut]  # first 100
    conflicts: list[ConflictOut]
    missing_rows: list[MissingOut]  # rows in the file with a draw number but no numbers
    headers_skipped: int
    warnings: list[str]
    message: str


class MissingDraws(BaseModel):
    game: str
    first_draw_no: int | None
    last_draw_no: int | None
    missing: list[int]
