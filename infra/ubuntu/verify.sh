#!/usr/bin/env bash
set -uo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/pulso-env.sh"

failures=0
warnings=0
pass() { printf 'PASS %-24s %s\n' "$1" "${2:-}"; }
fail() { printf 'FAIL %-24s %s\n' "$1" "${2:-}" >&2; failures=$((failures + 1)); }
warn() { printf 'WARN %-24s %s\n' "$1" "${2:-}"; warnings=$((warnings + 1)); }

require_command() {
  local name="$1"
  if command -v "${name}" >/dev/null 2>&1; then
    pass "command:${name}" "$(command -v "${name}")"
  else
    fail "command:${name}" "no encontrado"
  fi
}

optional_command() {
  local name="$1"
  if command -v "${name}" >/dev/null 2>&1; then
    pass "optional:${name}" "$(command -v "${name}")"
  else
    warn "optional:${name}" "no instalado"
  fi
}

require_ros_package() {
  local package="$1"
  if command -v ros2 >/dev/null 2>&1 && ros2 pkg prefix "${package}" >/dev/null 2>&1; then
    pass "ros:${package}"
  else
    fail "ros:${package}" "paquete ausente"
  fi
}

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" == "ubuntu" && "${VERSION_CODENAME:-}" == "jammy" ]]; then
    pass os "${PRETTY_NAME}"
  else
    fail os "se requiere Ubuntu 22.04 Jammy"
  fi
else
  fail os "/etc/os-release no disponible"
fi

for command_name in curl git java javac git-lfs python3 node npm adb sdkmanager blender \
  ros2 rosdep colcon ign rviz2 nc setsid sha256sum udevadm unzip; do
  require_command "${command_name}"
done
optional_command docker
optional_command nvidia-smi

if [[ "$(dpkg --print-architecture 2>/dev/null)" == "amd64" ]]; then
  pass architecture amd64
else
  fail architecture "se requiere amd64"
fi

if dpkg-query -W -f='${Status}' android-sdk-platform-tools-common 2>/dev/null | grep -Fq 'install ok installed'; then
  pass adb-udev-rules "android-sdk-platform-tools-common"
else
  fail adb-udev-rules "faltan reglas USB de Android"
fi
if id -nG | tr ' ' '\n' | grep -Fxq plugdev; then
  pass adb-usb-group plugdev
else
  warn adb-usb-group "plugdev no está activo; cierre sesión si install acaba de añadirlo"
fi

if [[ -d "${PULSO_DATA_ROOT}" && -w "${PULSO_DATA_ROOT}" ]]; then
  pass data-root "${PULSO_DATA_ROOT}"
else
  fail data-root "${PULSO_DATA_ROOT} no existe o no es escribible"
fi
if [[ -d "${PULSO_STATE_ROOT}" && -w "${PULSO_STATE_ROOT}" ]]; then
  pass state-root "${PULSO_STATE_ROOT}"
else
  fail state-root "${PULSO_STATE_ROOT} no existe o no es escribible"
fi

for java_dir in /usr/lib/jvm/java-17-openjdk-amd64 /usr/lib/jvm/java-21-openjdk-amd64; do
  [[ -x "${java_dir}/bin/java" ]] && pass "java:$(basename "${java_dir}")" || \
    fail "java:$(basename "${java_dir}")" "ausente"
done

if command -v node >/dev/null 2>&1; then
  node_major="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || echo 0)"
  (( node_major >= 18 )) && pass node-version "$(node --version)" || \
    fail node-version "se requiere Node 18+; encontrado $(node --version 2>/dev/null || echo desconocido)"
fi

if command -v java >/dev/null 2>&1; then
  java_major="$(java -version 2>&1 | awk -F'[\".]' '/version/ {print $2; exit}')"
  [[ "${java_major:-0}" =~ ^[0-9]+$ ]] && (( java_major >= 17 )) && \
    pass java-active "$(java -version 2>&1 | head -n 1)" || \
    fail java-active "se requiere Java 17+ activo"
fi
if [[ -x "${JAVA_HOME:-}/bin/java" ]]; then
  pass java-home "${JAVA_HOME}"
else
  fail java-home "JAVA_HOME no apunta a un JDK utilizable: ${JAVA_HOME:-unset}"
fi

if command -v sdkmanager >/dev/null 2>&1; then
  android_installed="$(sdkmanager --list_installed 2>/dev/null || true)"
  if grep -Fq "platforms;android-${PULSO_ANDROID_PLATFORM}" <<< "${android_installed}" && \
      grep -Fq "build-tools;${PULSO_ANDROID_BUILD_TOOLS}" <<< "${android_installed}" && \
      grep -Fq "platform-tools" <<< "${android_installed}"; then
    pass android-sdk "platform ${PULSO_ANDROID_PLATFORM}, build-tools ${PULSO_ANDROID_BUILD_TOOLS}, platform-tools"
  else
    fail android-sdk "componentes fijados incompletos"
  fi
else
  fail android-sdk "sdkmanager no disponible"
fi

for package in ros_gz_sim nav2_bringup slam_toolbox rosbridge_server; do
  require_ros_package "${package}"
done
if command -v rosdep >/dev/null 2>&1 && \
    rosdep check --from-paths "${PROJECT_ROOT}/sim/ros2_ws/src" --ignore-src >/dev/null 2>&1; then
  pass rosdep-workspace "dependencias resueltas"
else
  fail rosdep-workspace "dependencias ROS del workspace incompletas"
fi

if command -v ign >/dev/null 2>&1 && ign gazebo --versions 2>/dev/null | grep -Eq '(^|[^0-9])6\.'; then
  pass gazebo-fortress "ign-gazebo 6.x"
else
  fail gazebo-fortress "Gazebo Fortress / ign-gazebo 6.x no detectado"
fi

if [[ -x "${PULSO_PYTHON}" ]]; then
  if "${PULSO_PYTHON}" -c 'import litert_lm, websockets' >/dev/null 2>&1; then
    pass brain-python "${PULSO_PYTHON}"
  else
    fail brain-python "faltan litert_lm o websockets"
  fi
else
  fail brain-python "${PULSO_PYTHON} no existe"
fi

perception_python="${PULSO_DATA_ROOT}/venvs/perception/bin/python"
if [[ -x "${perception_python}" ]] && \
    "${perception_python}" -c 'import cv2, onnxruntime' >/dev/null 2>&1; then
  pass perception-python "${perception_python}"
else
  fail perception-python "runtime OpenCV/ONNX ausente"
fi

yolo_model="${PROJECT_ROOT}/apps/pulso-android/app/src/main/assets/models/yolo11n_pose.onnx"
if [[ -f "${yolo_model}" ]]; then
  actual_yolo_sha="$(sha256sum "${yolo_model}" | awk '{print $1}')"
  actual_yolo_bytes="$(wc -c < "${yolo_model}" | tr -d ' ')"
  if [[ "${actual_yolo_sha}" == "${PULSO_YOLO_SHA256}" && \
        "${actual_yolo_bytes}" == "${PULSO_YOLO_BYTES}" ]]; then
    pass yolo-pose "LFS materializado y fijado"
  else
    fail yolo-pose "hash/tamaño no coincide; ejecute git lfs pull"
  fi
else
  fail yolo-pose "asset ausente"
fi

if [[ -f "${PULSO_GEMMA_MODEL}" ]]; then
  actual_model_sha="$(sha256sum "${PULSO_GEMMA_MODEL}" | awk '{print $1}')"
  actual_model_bytes="$(wc -c < "${PULSO_GEMMA_MODEL}" | tr -d ' ')"
  if [[ "${actual_model_sha}" == "${PULSO_GEMMA_SHA256}" && \
        "${actual_model_bytes}" == "${PULSO_GEMMA_BYTES}" ]]; then
    pass gemma-e4b "hash y ${actual_model_bytes} bytes"
  else
    fail gemma-e4b "hash o tamaño no coincide"
  fi
else
  fail gemma-e4b "descargue con scripts/download_gemma4_e4b.sh ${PULSO_GEMMA_MODEL}"
fi

apk_path="${PULSO_APK:-${PROJECT_ROOT}/dist/${PULSO_APK_FILENAME}}"
if [[ -f "${apk_path}" ]]; then
  actual_apk_sha="$(sha256sum "${apk_path}" | awk '{print $1}')"
  actual_apk_bytes="$(wc -c < "${apk_path}" | tr -d ' ')"
  expected_apk_sha="${PULSO_LOCAL_APK_SHA256:-${PULSO_APK_SHA256}}"
  expected_apk_bytes="${PULSO_LOCAL_APK_BYTES:-${PULSO_APK_BYTES}}"
  if [[ "${actual_apk_sha}" == "${expected_apk_sha}" && \
        "${actual_apk_bytes}" == "${expected_apk_bytes}" ]]; then
    pass android-apk "artefacto fijado"
  else
    fail android-apk "artefacto distinto; no usar en la demo fijada"
  fi
else
  warn android-apk "${apk_path} no está provisionado"
fi

printf '\nRESULTADO failures=%d warnings=%d\n' "${failures}" "${warnings}"
exit "${failures}"
