from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.collect import router as collect_router
from app.api.backtests import router as backtests_router
from app.api.exports import router as exports_router
from app.api.picks import router as picks_router
from app.api.routes import router
from app.api.stats import router as stats_router
from app.config import get_settings
from app.db import get_session_factory
from app.games import seed_presets
from app.jobs import recover_interrupted_jobs
from app.scheduler import build_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    factory = get_session_factory()
    # Presets are inserted idempotently so a fresh database is usable immediately.
    with factory() as session:
        seed_presets(session)
        recover_interrupted_jobs(session)  # nothing survives a restart; do not leave 'running' rows
        session.commit()
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = build_scheduler(factory, settings)
        scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Royal Yellow Analyzer",
        description=(
            "Historical lottery analysis by Codencode Academy. Scores describe past "
            "behaviour; they are not probabilities of winning."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    app.include_router(collect_router)
    app.include_router(stats_router)
    app.include_router(picks_router)
    app.include_router(backtests_router)
    app.include_router(exports_router)
    return app


app = create_app()
