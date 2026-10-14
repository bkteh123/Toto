"""Command-line collector.

    python -m app.collect --game vn_mega_645                     # latest + gap-fill
    python -m app.collect --mode gaps
    python -m app.collect --mode verify --from 1453 --to 1574    # compare stored draws, insert nothing
"""

from __future__ import annotations

import argparse
import datetime as dt

from sqlalchemy import select

from app.collectors.factory import make_fetcher
from app.collectors.registry import get_collector
from app.collectors.runner import MODES, run_collect
from app.db import get_session_factory
from app.models import Game


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", default="vn_mega_645")
    ap.add_argument("--mode", choices=MODES, default="auto")
    ap.add_argument("--from", dest="from_no", type=int)
    ap.add_argument("--to", dest="to_no", type=int)
    ap.add_argument("--refresh", action="store_true", help="ignore the on-disk page cache")
    ap.add_argument("--today", type=dt.date.fromisoformat, help="override 'today' (YYYY-MM-DD)")
    args = ap.parse_args(argv)

    collector = get_collector(args.game)
    if collector is None:
        raise SystemExit(f"no collector for {args.game!r}")
    with get_session_factory()() as session:
        game = session.scalar(select(Game).where(Game.code == args.game))
        if game is None:
            raise SystemExit(f"unknown game {args.game!r}; run `python -m app.seed` first")
        res = run_collect(
            session, game, collector, make_fetcher(), mode=args.mode, today=args.today,
            from_no=args.from_no, to_no=args.to_no, refresh=args.refresh,
        )
        session.commit()

    print(f"status: {res.status}")
    print(res.message)
    for p in res.pages:
        print(f"  {p.status:<14} {p.date}  draws={p.draws:<3} {p.note}")
    print(f"added={res.added} matched={res.skipped} not_inserted={res.not_inserted} "
          f"rejected={res.rejected} conflicts={len(res.conflicts)}")
    for c in res.conflicts:
        print(f"  CONFLICT draw {c.draw_no} {c.draw_date}: stored {c.existing_numbers} vs source "
              f"{c.incoming_numbers} ({c.reason})")
    print(f"missing before: {res.missing_before or 'none'}")
    print(f"missing after : {res.missing_after or 'none'}")
    return {"ok": 0, "conflict": 1}.get(res.status, 2)


if __name__ == "__main__":
    raise SystemExit(main())
