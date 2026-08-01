#!/usr/bin/env bash
set -euo pipefail

readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"

fail() { echo "FAIL $*" >&2; exit 1; }
pass() { echo "PASS $*"; }

shell_files=(
  pulso
  infra/ubuntu/bootstrap.sh
  infra/ubuntu/pulso-env.sh
  infra/ubuntu/verify.sh
  infra/ubuntu/versions.env
  infra/ubuntu/run_real_bridge.sh
  scripts/pulso_cli.sh
  scripts/lib/pulso_processes.sh
  scripts/download_gemma4_e4b.sh
  scripts/install_brain_runtime.sh
  scripts/install_perception_runtime.sh
  scripts/android/push_model.sh
)
bash -n "${shell_files[@]}"
python3 -m py_compile infra/ubuntu/pulso_real_bridge.launch.py
pass "bash syntax"

for executable in pulso infra/ubuntu/bootstrap.sh infra/ubuntu/verify.sh infra/ubuntu/run_real_bridge.sh \
  scripts/pulso_cli.sh scripts/lib/pulso_processes.sh; do
  [[ -x "${executable}" ]] || fail "not executable: ${executable}"
done
pass "entrypoints executable"

help_output="$(./pulso --help)"
for command_name in install doctor sim real stop; do
  grep -Eq "(^|[[:space:]])${command_name}([[:space:]]|$)" <<< "${help_output}" || \
    fail "help omits ${command_name}"
done
pass "CLI contract"

if rg -n '/Users/|/home/[[:alnum:]_.-]+|diego@' \
    infra scripts documentation docs README.md \
    --glob '!scripts/android/**' --glob '!scripts/tests/pulso_delivery_test.sh' \
    --glob '!documentation/design/**'; then
  fail "hard-coded user path"
fi
pass "portable paths"

grep -Fq "resolve/\${PULSO_GEMMA_REVISION}/" scripts/download_gemma4_e4b.sh || \
  fail "Gemma download is not revision-pinned"
grep -Fq 'PULSO_ANDROID_TOOLS_SHA256=' infra/ubuntu/versions.env || \
  fail "Android tools checksum missing"
grep -Fq 'PULSO_YOLO_SHA256=' infra/ubuntu/versions.env || \
  fail "YOLO checksum missing"
grep -Fq 'android-sdk-platform-tools-common' infra/ubuntu/bootstrap.sh || \
  fail "ADB udev rules are not installed"
grep -Fq 'add-apt-repository universe' infra/ubuntu/bootstrap.sh || \
  fail "Ubuntu universe bootstrap missing"
universe_line="$(grep -n 'add-apt-repository universe' infra/ubuntu/bootstrap.sh | head -n1 | cut -d: -f1)"
opencv_line="$(grep -n 'python3-opencv' infra/ubuntu/bootstrap.sh | head -n1 | cut -d: -f1)"
(( universe_line < opencv_line )) || fail "universe is enabled after universe packages"
grep -Fq 'rosdep install --from-paths' infra/ubuntu/bootstrap.sh || \
  fail "workspace rosdep install missing"
pass "artifact pins"

if rg -n 'cmd_vel|move_to|look_at|motor.*(start|forward|speed)' scripts/pulso_cli.sh; then
  fail "real-mode CLI contains a motion command"
fi
grep -Fq 'ZEUS=DRY_RUN' scripts/pulso_cli.sh || fail "Zeus dry-run boundary missing"
grep -Fq 'class AndroidRealSource' \
  apps/pulso-android/app/src/main/java/com/pulso/app/sensor/real/AndroidRealSource.kt || \
  fail "AndroidReal source missing"
android_real_source="apps/pulso-android/app/src/main/java/com/pulso/app/sensor/real/AndroidRealSource.kt"
real_telemetry="apps/pulso-android/app/src/main/java/com/pulso/app/sensor/real/RealTelemetry.kt"
phone_torch="apps/pulso-android/app/src/main/java/com/pulso/app/robot/PhoneTorchActuator.kt"
phone_audio="apps/pulso-android/app/src/main/java/com/pulso/app/audio/PhoneAudioActuator.kt"
gemma_runtime="apps/pulso-android/app/src/main/java/com/pulso/app/runtime/GemmaRuntime.kt"

grep -Fq 'acquireCameraImage' "${android_real_source}" || fail "AndroidReal RGB missing"
grep -Fq 'acquireDepthImage16Bits' "${android_real_source}" || fail "AndroidReal Depth missing"
grep -Fq 'displayOrientedPose' "${android_real_source}" || fail "AndroidReal VIO pose missing"
grep -Fq 'Sensor.TYPE_ACCELEROMETER' "${real_telemetry}" || fail "AndroidReal accelerometer missing"
grep -Fq 'Sensor.TYPE_GYROSCOPE' "${real_telemetry}" || fail "AndroidReal gyroscope missing"
grep -Fq 'setTorchMode' "${phone_torch}" || fail "phone torch actuator missing"
grep -Fq 'TextToSpeech' "${phone_audio}" || fail "phone TTS actuator missing"
grep -Fq 'AudioRecord' "${phone_audio}" || fail "phone audio capture missing"
grep -Fq 'class GemmaRuntime' "${gemma_runtime}" || fail "local Gemma runtime missing"
pass "ANDROID_REAL implementation surface"

grep -Fq 'val dryRun: Boolean = true' \
  apps/pulso-android/app/src/main/java/com/pulso/app/robot/ZeusWebSocketClient.kt || \
  fail "Zeus default is not dry-run"
grep -Fq 'STOP_ATTEMPTED_UNCONFIRMED' \
  apps/pulso-android/app/src/main/java/com/pulso/app/robot/ZeusWebSocketClient.kt || \
  fail "Zeus STOP uncertainty missing"
pass "physical-motion boundary"

real_bridge="infra/ubuntu/run_real_bridge.sh"
grep -Fq 'address:=127.0.0.1' "${real_bridge}" || fail "REAL bridge not loopback-only"
grep -Fq 'services_glob:="[]"' "${real_bridge}" || fail "REAL services not denied"
grep -Fq 'actions_glob:="[]"' "${real_bridge}" || fail "REAL actions not denied"
if rg -n '/pulso/hil/action_intent' "${real_bridge}"; then
  fail "REAL bridge exposes action_intent"
fi
grep -Fq 'run_real_bridge.sh' scripts/pulso_cli.sh || \
  fail "pulso real does not use the restricted bridge"
grep -Fq 'device_physical_preflight' scripts/pulso_cli.sh || \
  fail "S25 physical preflight missing"
grep -Fq 'pm path com.google.ar.core' scripts/pulso_cli.sh || \
  fail "S25 ARCore guard missing"
grep -Fq 'PULSO_GEMMA_BYTES + 1073741824' scripts/pulso_cli.sh || \
  fail "S25 model storage guard missing"
grep -Fq 'ANDROID_SERIAL="${ADB_SERIAL}"' scripts/pulso_cli.sh || \
  fail "model push is not bound to the validated S25"
pass "REAL telemetry bridge"

doc_scope=(README.md documentation/*.md apps/pulso-android/README.md apps/pulso-mission-control/README.md)
if rg -n '\?demo=1|0\.0\.0\.0|192\.168\.18\.51|\bLAN\b' "${doc_scope[@]}"; then
  fail "obsolete network/demo documentation"
fi
if rg -n -i 'ANDROID_REAL.{0,40}(sin implementar|no implement|unimplemented|placeholder)' \
    "${doc_scope[@]}"; then
  fail "stale AndroidReal status"
fi
grep -Fq 'runtime' apps/pulso-android/README.md || fail "S25 runtime caveat missing"
for command_name in install doctor sim real; do
  grep -Fq "./pulso ${command_name}" README.md || fail "README omits ./pulso ${command_name}"
done
grep -Fq 'corrida runtime completa' apps/pulso-android/README.md || \
  fail "AndroidReal runtime non-validation is not explicit"
grep -Fq 'dry-run' apps/pulso-android/README.md || fail "Zeus dry-run caveat missing"
grep -Fq 'no tiene ACK' apps/pulso-android/README.md || fail "Zeus STOP caveat missing"
pass "delivery documentation truth"

canonical_mesh="sim/ros2_ws/src/pulso_gazebo/models/pulso_disaster_scene/meshes/pulso_disaster_visual.dae"
git check-ignore "${canonical_mesh}" >/dev/null 2>&1 && fail "canonical sim mesh ignored"
attributes="$(git check-attr filter -- "${canonical_mesh}")"
grep -Fq 'filter: lfs' <<< "${attributes}" || fail "canonical sim mesh not in LFS"
git check-ignore art/current/ragdoll/seed_20260731/pulso_ragdoll_seed_20260731.blend >/dev/null || \
  fail "legacy Blender seed not ignored"
pass "Git hygiene"

# The APK is intentionally outside Git; verify it when provisioned locally.
if [[ -f dist/pulso-debug.apk ]]; then
  # shellcheck disable=SC1091
  source infra/ubuntu/versions.env
  actual_sha="$(sha256sum dist/pulso-debug.apk | awk '{print $1}')"
  actual_bytes="$(wc -c < dist/pulso-debug.apk | tr -d ' ')"
  [[ "${actual_sha}" == "${PULSO_APK_SHA256}" ]] || fail "local APK hash"
  [[ "${actual_bytes}" == "${PULSO_APK_BYTES}" ]] || fail "local APK size"
  pass "local APK pin"
else
  echo "SKIP local APK not provisioned"
fi

echo "RESULT pulso delivery checks passed"
