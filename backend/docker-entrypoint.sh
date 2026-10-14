#!/bin/sh
# Apply migrations, optionally load the seed history, then start the server.
set -e

echo "Applying database migrations..."
alembic upgrade head

# The seed is idempotent: draws that already exist are skipped, and a draw that disagrees
# with a stored one is reported as a conflict instead of being overwritten.
if [ "${SEED_ON_START:-true}" = "true" ] && [ -f "${SEED_CSV:-/seed/mega645.csv}" ]; then
    echo "Loading seed history from ${SEED_CSV:-/seed/mega645.csv}..."
    python -m app.seed --csv "${SEED_CSV:-/seed/mega645.csv}" --game vn_mega_645 \
        --first-draw-no "${SEED_FIRST_DRAW_NO:-1453}" || echo "Seed reported a problem (see above); starting anyway."
fi

exec "$@"
