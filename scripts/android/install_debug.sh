#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 2 ]]; then
  echo "Usage: $0 [/absolute/path/to/pulso-debug.apk] [/absolute/path/to/gemma-4-E4B-it.litertlm]" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
apk_path="${1:-${repo_root}/dist/pulso-debug.apk}"
default_data_root="${PULSO_DATA_ROOT:-${XDG_DATA_HOME:-${HOME}/.local/share}/pulso}"
model_path="${2:-${default_data_root}/models/gemma-4-E4B-it.litertlm}"
if [[ ! -f "${apk_path}" ]]; then
  echo "APK not found: ${apk_path}" >&2
  exit 1
fi

device_count="$(adb devices | awk 'NR > 1 && $2 == "device" {count++} END {print count + 0}')"
if [[ "${device_count}" -ne 1 ]]; then
  echo "Expected exactly one authorized Android device; found ${device_count}." >&2
  adb devices -l >&2
  exit 1
fi

adb install -r -t "${apk_path}"
"${script_dir}/push_model.sh" "${model_path}"
if ! adb shell pm path com.google.ar.core >/dev/null 2>&1; then
  echo "Google Play Services for AR is missing; install/update it before ANDROID_REAL." >&2
  exit 1
fi
adb shell pm grant com.pulso.app android.permission.CAMERA
adb shell pm grant com.pulso.app android.permission.RECORD_AUDIO
adb reverse tcp:9091 tcp:9091
adb shell settings put global stay_on_while_plugged_in 7
adb shell svc power stayon true
adb shell am force-stop com.pulso.app
adb shell monkey -p com.pulso.app -c android.intent.category.LAUNCHER 1 >/dev/null
echo "Pulso installed and launched; rosbridge is available to the phone at ws://127.0.0.1:9091."
