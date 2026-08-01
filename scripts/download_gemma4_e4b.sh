#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "${project_root}/infra/ubuntu/versions.env"

default_data_root="${PULSO_DATA_ROOT:-${XDG_DATA_HOME:-${HOME}/.local/share}/pulso}"
destination="${1:-${default_data_root}/models/${PULSO_GEMMA_FILENAME}}"
expected_sha256="${2:-${PULSO_GEMMA_SHA256}}"
url="https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/resolve/${PULSO_GEMMA_REVISION}/${PULSO_GEMMA_FILENAME}?download=true"
partial="${destination}.part"
download_log="${destination}.download.log"

mkdir -p "$(dirname "${destination}")"
if [[ -f "${destination}" ]]; then
  current_sha="$(sha256sum "${destination}" | awk '{print $1}')"
  current_bytes="$(wc -c < "${destination}" | tr -d ' ')"
  if [[ "${current_sha}" == "${expected_sha256}" && "${current_bytes}" == "${PULSO_GEMMA_BYTES}" ]]; then
    printf 'VERIFIED existing path=%s bytes=%s sha256=%s\n' \
      "${destination}" "${current_bytes}" "${current_sha}"
    exit 0
  fi
fi
curl \
  --fail \
  --location \
  --retry 8 \
  --retry-all-errors \
  --continue-at - \
  --output "${partial}" \
  "${url}" 2>&1 | tee "${download_log}"

actual_sha256="$(sha256sum "${partial}" | awk '{print $1}')"
actual_bytes="$(wc -c < "${partial}" | tr -d ' ')"
printf '%s  %s\n' "${actual_sha256}" "$(basename "${destination}")" > "${destination}.sha256"

if [[ "${actual_sha256}" != "${expected_sha256}" || "${actual_bytes}" != "${PULSO_GEMMA_BYTES}" ]]; then
  printf 'ARTIFACT_MISMATCH expected_sha=%s actual_sha=%s expected_bytes=%s actual_bytes=%s\n' \
    "${expected_sha256}" "${actual_sha256}" "${PULSO_GEMMA_BYTES}" "${actual_bytes}" >&2
  exit 42
fi

mv "${partial}" "${destination}"
printf 'VERIFIED path=%s bytes=%s sha256=%s\n' \
  "${destination}" \
  "${actual_bytes}" \
  "${actual_sha256}"
