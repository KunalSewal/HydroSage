#!/usr/bin/env bash
# One analysis API instance (app.analyze_only) for the four-container
# deployment -- see docs/DEPLOYMENT.md. Restarts the server whenever it
# exits: the app deliberately restarts itself to hand memory back once its
# resident floor climbs too high for the 512 MB cap (D-012), and a restart
# also recovers from an OOM kill.
set -u
cd "$(dirname "$0")/../backend"
source .venv/bin/activate

export MALLOC_ARENA_MAX=2                 # fewer glibc arenas, less RSS (D-012)
export REDIS_URL=""                       # no Redis here: in-process catchment cache
export DEM_CACHE_DIR="${DEM_CACHE_DIR:-$HOME/.hydrosage-dem-cache}"  # no MinIO: DEMs cached on disk
PORT="${PORT:-3000}"

while true; do
  uvicorn app.analyze_only:app --host 0.0.0.0 --port "$PORT"
  echo "[run_api] server exited ($?); restarting in 2 s" >&2
  sleep 2
done
