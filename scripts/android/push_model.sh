#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/../.." && pwd)"
# shellcheck disable=SC1091
source "${project_root}/infra/ubuntu/versions.env"

if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [/absolute/path/to/gemma-4-E4B-it.litertlm]" >&2
  exit 2
fi

default_data_root="${PULSO_DATA_ROOT:-${XDG_DATA_HOME:-${HOME}/.local/share}/pulso}"
model_path="${1:-${default_data_root}/models/${PULSO_GEMMA_FILENAME}}"
expected_sha256="${PULSO_GEMMA_SHA256}"
if [[ ! -f "${model_path}" ]]; then
  echo "Model file not found: ${model_path}" >&2
  exit 1
fi

printf '%s  %s\n' "${expected_sha256}" "${model_path}" | sha256sum --check -

package_id="com.pulso.app"
device_dir="/storage/emulated/0/Android/data/${package_id}/files/models"
# Creating this directory as `adb shell` leaves it owned by `shell`, which the
# normal app process cannot traverse on Samsung's scoped-storage mount. Create
# it under the app UID instead; the model itself remains external to the APK.
adb shell run-as "${package_id}" mkdir -p "${device_dir}"
device_dir_owner="$(adb shell stat -c '%U' "${device_dir}" | tr -d '\r')"
if [[ "${device_dir_owner}" == "shell" ]]; then
  echo "Model directory is not app-owned: ${device_dir}" >&2
  exit 1
fi
device_model="${device_dir}/${PULSO_GEMMA_FILENAME}"
existing_sha256="$(adb shell sha256sum "${device_model}" 2>/dev/null | tr -d '\r' | awk '{print $1}' || true)"
if [[ "${existing_sha256}" == "${expected_sha256}" ]]; then
  echo "Gemma 4 E4B already matches on device; skipping 3.66 GB transfer."
  exit 0
fi
adb push "${model_path}" "${device_model}"
adb shell ls -lh "${device_model}"
device_sha256="$(adb shell sha256sum "${device_model}" | tr -d '\r' | awk '{print $1}')"
if [[ "${device_sha256}" != "${expected_sha256}" ]]; then
  echo "Device model hash mismatch: ${device_sha256}" >&2
  exit 1
fi
echo "Model SHA-256 verified on device."
