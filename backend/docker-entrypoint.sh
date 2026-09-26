#!/bin/sh
set -e
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi
if [ "${RUN_SEED:-true}" = "true" ]; then
  python -m app.seed
fi
exec "$@"
