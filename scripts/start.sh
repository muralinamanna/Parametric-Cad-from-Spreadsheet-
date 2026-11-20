#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f frontend/dist/index.html ]; then
    (cd frontend && npm ci && npm run build)
fi
export PYTHONPATH="backend${PYTHONPATH:+:$PYTHONPATH}"
exec python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
