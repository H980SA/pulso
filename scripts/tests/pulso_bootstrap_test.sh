#!/usr/bin/env bash
set -euo pipefail

readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"

fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }
pass() { printf 'PASS %s\n' "$*"; }
line_of() { grep -n -m1 -F "$1" "$2" | cut -d: -f1; }

bash -n pulso infra/ubuntu/bootstrap.sh infra/ubuntu/pulso-env.sh \
  infra/ubuntu/verify.sh infra/ubuntu/run_real_bridge.sh scripts/pulso_cli.sh \
  scripts/lib/pulso_processes.sh scripts/android/push_model.sh
pass "shell syntax"

env_reload_output="$(bash -c 'source infra/ubuntu/pulso-env.sh; source infra/ubuntu/pulso-env.sh' 2>&1)"
[[ -z "${env_reload_output}" ]] || fail "pulso-env is not idempotent: ${env_reload_output}"
pass "environment reload"

universe_line="$(line_of 'add-apt-repository universe' infra/ubuntu/bootstrap.sh)"
opencv_line="$(line_of 'python3-opencv' infra/ubuntu/bootstrap.sh)"
(( universe_line < opencv_line )) || fail "universe packages precede repository enablement"
grep -Fq 'android-sdk-platform-tools-common' infra/ubuntu/bootstrap.sh || fail "ADB udev package missing"
grep -Fq 'usermod -aG plugdev' infra/ubuntu/bootstrap.sh || fail "plugdev enrollment missing"
grep -Fq 'export JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"' infra/ubuntu/bootstrap.sh || \
  fail "pinned bootstrap JDK missing"
grep -Fq 'rosdep install --from-paths' infra/ubuntu/bootstrap.sh || fail "rosdep install missing"
if rg -n 'Dir::Cache::archives|chown _apt' infra/ubuntu/bootstrap.sh; then
  fail "APT sandbox cache is nested under the user data root"
fi
pass "clean Ubuntu dependency order and permissions"

grep -Fq 'PULSO_YOLO_SHA256=' infra/ubuntu/versions.env || fail "YOLO pin missing"
grep -Fq 'PULSO_ANDROID_TOOLS_SHA256=' infra/ubuntu/versions.env || fail "Android tools pin missing"
grep -Fq 'PULSO_NODE_LINUX_X64_SHA256=' infra/ubuntu/versions.env || fail "Node pin missing"
grep -Fq 'rev-parse --is-inside-work-tree' infra/ubuntu/bootstrap.sh || fail "Git worktree detection missing"
grep -Fq 'git -C "${PROJECT_ROOT}" lfs pull' infra/ubuntu/bootstrap.sh || fail "LFS materialization missing"
# shellcheck disable=SC1091
source infra/ubuntu/versions.env
yolo_model="apps/pulso-android/app/src/main/assets/models/yolo11n_pose.onnx"
[[ "$(sha256sum "${yolo_model}" | awk '{print $1}')" == "${PULSO_YOLO_SHA256}" ]] || fail "YOLO hash drift"
[[ "$(wc -c < "${yolo_model}" | tr -d ' ')" == "${PULSO_YOLO_BYTES}" ]] || fail "YOLO size drift"
pass "download integrity pins"

preflight_line="$(grep -n -m1 '^  device_physical_preflight$' scripts/pulso_cli.sh | cut -d: -f1)"
dry_return_line="$(line_of 'if (( dry_run == 1 ))' scripts/pulso_cli.sh)"
(( preflight_line < dry_return_line )) || fail "dry-run returns before physical preflight"
grep -Fq 'pm path com.google.ar.core' scripts/pulso_cli.sh || fail "ARCore guard missing"
grep -Fq 'android.hardware.sensor.gyroscope' scripts/pulso_cli.sh || fail "gyro guard missing"
grep -Fq 'PULSO_GEMMA_BYTES + 1073741824' scripts/pulso_cli.sh || fail "device storage guard missing"
grep -Fq 'ANDROID_SERIAL="${ADB_SERIAL}"' scripts/pulso_cli.sh || fail "validated serial not bound to model push"
if rg -n 'cmd_vel|motor.*(start|forward|speed)' scripts/pulso_cli.sh; then
  fail "physical CLI contains motion command"
fi
pass "physical dry-run guards and no-motion boundary"

grep -Fq 'source "${project_root}/infra/ubuntu/versions.env"' scripts/android/push_model.sh || \
  fail "model push duplicates artifact pins"
grep -Fq 'adb-udev-rules' infra/ubuntu/verify.sh || fail "doctor omits ADB rules"
grep -Fq 'rosdep-workspace' infra/ubuntu/verify.sh || fail "doctor omits workspace dependencies"
grep -Fq 'java-active' infra/ubuntu/verify.sh || fail "doctor omits active JDK"
pass "doctor coverage"

echo "RESULT bootstrap and physical-operation checks passed"
