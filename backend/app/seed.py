"""Load the preset games and a seed CSV (`date,n1..nK`) into the database.

    python -m app.seed --csv ../seed/mega645.csv --game vn_mega_645 --first-draw-no 1453

`--first-draw-no` numbers the rows by position, which is only correct when the CSV has no
gaps. Check it against a source you trust (the Excel grid carries real draw numbers) before
relying on it. Without the flag, draws are stored by date only.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from app.db import get_session_factory
from app.games import seed_presets
from app.importers.service import missing_draw_numbers, store_draws
from app.importers.text_csv import parse_text
from app.models import Game
from app.validation import GameSpec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=Path("../seed/mega645.csv"))
    ap.add_argument("--game", default="vn_mega_645")
    ap.add_argument("--first-draw-no", type=int, default=None)
    args = ap.parse_args(argv)

    with get_session_factory()() as session:
        added_presets = seed_presets(session)
        game = session.scalar(select(Game).where(Game.code == args.game))
        if game is None:
            raise SystemExit(f"unknown game {args.game!r}")
        parsed = parse_text(args.csv.read_text(encoding="utf-8-sig"), GameSpec.from_model(game))
        if parsed.rejected:
            for r in parsed.rejected:
                print(f"REJECTED line {r.line_no}: {r.reason}")
            raise SystemExit("seed file has rejected rows; fix them first")
        dates = [d.draw_date for d in parsed.draws]
        if any(d is None for d in dates) or dates != sorted(set(dates)):
            raise SystemExit("seed rows must have unique, ascending dates")
        if args.first_draw_no is not None:
            for i, d in enumerate(parsed.draws):
                d.draw_no = args.first_draw_no + i
        out = store_draws(session, game, parsed.draws, source=f"seed: {args.csv.name}", kind="file")
        session.commit()
        print(f"presets added: {added_presets}")
        print(f"status={out.status} added={out.added} skipped={out.skipped} "
              f"rejected={len(out.rejected)} conflicts={len(out.conflicts)}")
        for c in out.conflicts:
            print(f"CONFLICT draw {c.draw_no} {c.draw_date}: stored {c.existing_numbers} vs file {c.incoming_numbers}")
        gaps = missing_draw_numbers(session, game)
        print(f"missing draw numbers: {gaps if gaps else 'none'}")
        return 0 if out.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
