#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "${project_root}/infra/ubuntu/pulso-env.sh"

venv_dir="${PULSO_DATA_ROOT}/venvs/litert-lm-py310"
python3 -m venv "${venv_dir}"
"${venv_dir}/bin/python" -m pip install --disable-pip-version-check --no-cache-dir \
  "litert-lm-api==0.13.1" \
  "websockets==15.0.1"
"${venv_dir}/bin/python" - <<'PY'
import importlib.metadata
import litert_lm
import websockets

print("litert-lm-api", importlib.metadata.version("litert-lm-api"))
print("websockets", websockets.__version__)
print("module", litert_lm.__file__)
PY
