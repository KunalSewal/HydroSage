#!/usr/bin/env bash
# The gateway (app.gateway): serves the built frontend and load-balances
# API calls across the analysis instances -- see docs/DEPLOYMENT.md.
#
#   GATEWAY_BACKENDS=http://10.1.75.53:3267,http://10.1.75.53:3268 ./deploy/run_gateway.sh
set -u
cd "$(dirname "$0")/../backend"
source .venv/bin/activate

: "${GATEWAY_BACKENDS:?set GATEWAY_BACKENDS to the API instances, comma-separated}"
export GATEWAY_BACKENDS
export GATEWAY_STATIC_DIR="${GATEWAY_STATIC_DIR:-$HOME/hydrosage-web}"
PORT="${PORT:-3000}"

while true; do
  uvicorn app.gateway:app --host 0.0.0.0 --port "$PORT"
  echo "[run_gateway] server exited ($?); restarting in 2 s" >&2
  sleep 2
done
