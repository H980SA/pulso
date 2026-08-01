#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "${project_root}/infra/ubuntu/pulso-env.sh"

venv_dir="${PULSO_DATA_ROOT}/venvs/perception"
python3 -m venv "${venv_dir}"
"${venv_dir}/bin/python" -m pip install 'pip==25.2'
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  "${venv_dir}/bin/python" -m pip install \
    'onnxruntime-gpu[cuda,cudnn]==1.23.2' \
    'opencv-python-headless==4.12.0.88'
else
  "${venv_dir}/bin/python" -m pip install \
    'onnxruntime==1.23.2' \
    'opencv-python-headless==4.12.0.88'
fi

"${venv_dir}/bin/python" - <<'PY'
import onnxruntime as ort

if "CUDAExecutionProvider" in ort.get_available_providers():
    ort.preload_dlls(directory="")
providers = ort.get_available_providers()
print("PULSO perception runtime ready:", providers)
PY
