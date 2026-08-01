#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
hil_url="${1:-${PULSO_HIL_URL:-ws://127.0.0.1:9091}}"
output_path="${2:-${repo_root}/dist/pulso-debug.apk}"

case "${hil_url}" in
  ws://*|wss://*) ;;
  *)
    echo "HIL URL must use ws:// or wss://: ${hil_url}" >&2
    exit 2
    ;;
esac

mkdir -p "$(dirname "${output_path}")"
cd "${repo_root}/apps/pulso-android"
./gradlew --no-daemon \
  -PpulsoHilUrl="${hil_url}" \
  testDebugUnitTest assembleDebug
install -m 0644 app/build/outputs/apk/debug/app-debug.apk "${output_path}"

sha256sum "${output_path}"
ls -lh "${output_path}"
echo "HIL endpoint embedded in BuildConfig: ${hil_url}"
