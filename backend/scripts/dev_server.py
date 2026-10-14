"""Run the API locally without Docker or an installed PostgreSQL.

    cd backend
    python scripts/dev_server.py            # http://127.0.0.1:8000  (docs at /docs)

Starts an embedded PostgreSQL 16 (the `pgserver` package from requirements-dev.txt), applies
the migrations, loads ../seed/mega645.csv (idempotent) and serves the API with uvicorn.
Data persists between runs in ~/.royal-yellow/pgdata (outside OneDrive-synced folders).
Use a real PostgreSQL instead by setting DATABASE_URL and running uvicorn directly.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--data-dir", type=Path, default=Path.home() / ".royal-yellow" / "pgdata")
    ap.add_argument("--no-seed", action="store_true", help="do not load seed/mega645.csv")
    ap.add_argument("--scheduler", action="store_true", help="enable the scheduled result updates")
    args = ap.parse_args()

    try:
        import pgserver
    except ImportError:
        raise SystemExit("pgserver is not installed: pip install -r backend/requirements-dev.txt")

    args.data_dir.parent.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(args.data_dir, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+psycopg://")
    os.environ["DATABASE_URL"] = url
    os.environ["SCHEDULER_ENABLED"] = "true" if args.scheduler else "false"

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    if not args.no_seed:
        from app import seed

        seed.main(["--csv", str(BACKEND.parent / "seed" / "mega645.csv"),
                   "--game", "vn_mega_645", "--first-draw-no", "1453"])

    import uvicorn

    print(f"\nAPI: http://127.0.0.1:{args.port}   (docs: /docs)   data: {args.data_dir}\n")
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
