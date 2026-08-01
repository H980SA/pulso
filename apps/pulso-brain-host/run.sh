#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$APP_DIR/../.." && pwd)"
if [[ -n "${PULSO_PYTHON:-}" ]]; then
  PYTHON_BIN="${PULSO_PYTHON}"
elif [[ -x "$PROJECT_ROOT/.tools/venvs/litert-lm-py313/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_ROOT/.tools/venvs/litert-lm-py313/bin/python"
else
  PYTHON_BIN="$PROJECT_ROOT/.tools/venvs/litert-lm-py310/bin/python"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing Python 3.10+ LiteRT runtime: $PYTHON_BIN" >&2
  exit 2
fi

export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONFAULTHANDLER="${PYTHONFAULTHANDLER:-1}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
exec "$PYTHON_BIN" -X faulthandler -m pulso_brain_host.main "$@"
