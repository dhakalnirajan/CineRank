#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

COMMAND="${1:-api}"
shift || true

if [[ ! -d .venv ]]; then
  python -m venv .venv
fi

# --- Activate venv in a cross-platform way (Windows vs Unix) ---
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    ACTIVATE=".venv/Scripts/activate"
    ;;
  *)
    ACTIVATE=".venv/bin/activate"
    ;;
esac

if [[ ! -f "$ACTIVATE" ]]; then
  echo "ERROR: venv activation script not found at $ACTIVATE" >&2
  echo "       Try: rm -rf .venv && ./run.sh $COMMAND" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ACTIVATE"
python -m pip install --upgrade pip
pip install -r requirements.txt

case "$COMMAND" in
  api)
    export AUTO_CREATE_SCHEMA="${AUTO_CREATE_SCHEMA:-false}"
    exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --no-access-log "$@"
    ;;
  worker)
    export AUTO_CREATE_SCHEMA="${AUTO_CREATE_SCHEMA:-false}"
    exec python -m app.worker "$@"
    ;;
  migrate)
    exec alembic upgrade head "$@"
    ;;
  train)
    exec python scripts/prepare_and_train.py "$@"
    ;;
  import)
    exec python scripts/import_colab_bundle.py "$@"
    ;;
  *)
    echo "Usage: ./run.sh {api|worker|migrate|train|import} [arguments]" >&2
    exit 2
    ;;
esac