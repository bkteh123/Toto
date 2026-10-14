from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Game

DEFAULT_GAME_CODE = "vn_mega_645"

PRESETS: list[dict] = [
    dict(code="vn_mega_645", name="Vietlott Mega 6/45", max_number=45, pick_count=6,
         has_bonus=False, bonus_max=None, ticket_price=Decimal("10000"), currency="VND", is_default=True),
    dict(code="vn_power_655", name="Vietlott Power 6/55", max_number=55, pick_count=6,
         has_bonus=True, bonus_max=55, ticket_price=Decimal("10000"), currency="VND"),
    dict(code="my_power_toto_655", name="Sports Toto Power Toto 6/55", max_number=55, pick_count=6,
         has_bonus=False, bonus_max=None, ticket_price=Decimal("1"), currency="MYR"),
    dict(code="generic_650", name="Generic 6/50", max_number=50, pick_count=6,
         has_bonus=False, bonus_max=None, ticket_price=Decimal("1"), currency="UNIT"),
]


def seed_presets(session: Session) -> int:
    """Insert missing presets (idempotent). Existing rows are left untouched."""
    existing = set(session.scalars(select(Game.code)))
    added = 0
    for p in PRESETS:
        if p["code"] in existing:
            continue
        session.add(Game(is_preset=True, **p))
        added += 1
    session.flush()
    return added
