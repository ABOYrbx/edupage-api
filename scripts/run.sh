#!/usr/bin/env sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

MODE=${1:-dev}
if [ "$MODE" = "prod" ]; then
  cd backend
  ../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8787
else
  # dev: backend + frontend
  cd backend
  ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8787 &
  API_PID=$!
  cd "$ROOT_DIR/frontend"
  npm run dev &
  WEB_PID=$!
  trap 'kill $API_PID $WEB_PID 2>/dev/null' EXIT INT TERM
  wait
fi
