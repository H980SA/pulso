#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
robot_host="${1:-exomy@10.245.145.36}"
robot_url="${2:-http://10.245.145.36:8765}"
output_path="${3:-${repo_root}/dist/pulso-field-debug.apk}"
ssh_key="${PULSO_ROBOT_SSH_KEY:-${HOME}/.ssh/pulso_robot_ed25519}"

[[ "${robot_url}" == http://* || "${robot_url}" == https://* ]] || {
  echo "Rover URL must use http:// or https://" >&2
  exit 2
}
token="$(ssh -i "${ssh_key}" -o BatchMode=yes -o ConnectTimeout=5 "${robot_host}" \
  'sudo -n cat /etc/pulso-rover/api-token')"
[[ -n "${token}" ]] || { echo "Robot pairing credential was empty" >&2; exit 1; }

mkdir -p "$(dirname "${output_path}")"
if [[ -z "${JAVA_HOME:-}" && -d "${repo_root}/.tools/jdk" ]]; then
  export JAVA_HOME="${repo_root}/.tools/jdk"
  export PATH="${JAVA_HOME}/bin:${PATH}"
fi
if [[ -z "${ANDROID_HOME:-}" && -d "${repo_root}/.tools/android-sdk" ]]; then
  export ANDROID_HOME="${repo_root}/.tools/android-sdk"
  export PATH="${ANDROID_HOME}/platform-tools:${PATH}"
fi
cd "${repo_root}/apps/pulso-android"
PULSO_ROVER_TOKEN="${token}" \
PULSO_ROVER_URL="${robot_url}" \
PULSO_ROVER_ACTUATION_ENABLED=true \
PULSO_HIL_URL="${PULSO_HIL_URL:-ws://172.20.10.7:9091}" \
PULSO_SIM_HIL_URL="${PULSO_SIM_HIL_URL:-ws://172.20.10.7:9092}" \
  ./gradlew --no-daemon testDebugUnitTest assembleDebug
install -m 0644 app/build/outputs/apk/debug/app-debug.apk "${output_path}"
unset token PULSO_ROVER_TOKEN
sha256sum "${output_path}"
ls -lh "${output_path}"
echo "Field APK built for ${robot_url}; credential was provisioned automatically and was not printed."
