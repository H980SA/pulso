#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "Use: source ./infra/ubuntu/pulso-env.sh" >&2
  exit 2
fi

_pulso_env_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_pulso_project_root="$(cd "${_pulso_env_dir}/../.." && pwd)"
# shellcheck disable=SC1091
source "${_pulso_env_dir}/versions.env"

export PULSO_PROJECT_ROOT="${PULSO_PROJECT_ROOT:-${_pulso_project_root}}"
export PULSO_DATA_ROOT="${PULSO_DATA_ROOT:-${XDG_DATA_HOME:-${HOME}/.local/share}/pulso}"
export PULSO_STATE_ROOT="${PULSO_STATE_ROOT:-${XDG_STATE_HOME:-${HOME}/.local/state}/pulso}"
export GRADLE_USER_HOME="${GRADLE_USER_HOME:-${PULSO_DATA_ROOT}/cache/gradle}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-${PULSO_DATA_ROOT}/cache/pip}"
export GZ_FUEL_CACHE_PATH="${GZ_FUEL_CACHE_PATH:-${PULSO_DATA_ROOT}/cache/gazebo/fuel}"
export IGN_FUEL_CACHE_PATH="${IGN_FUEL_CACHE_PATH:-${GZ_FUEL_CACHE_PATH}}"
export ANDROID_HOME="${ANDROID_HOME:-${PULSO_ANDROID_SDK_ROOT:-${PULSO_DATA_ROOT}/android-sdk}}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME}}"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
export PULSO_PERCEPTION_SITE_PACKAGES="${PULSO_PERCEPTION_SITE_PACKAGES:-${PULSO_DATA_ROOT}/venvs/perception/lib/python3.10/site-packages}"
export PULSO_YOLO_MODEL="${PULSO_YOLO_MODEL:-${PULSO_PROJECT_ROOT}/apps/pulso-android/app/src/main/assets/models/yolo11n_pose.onnx}"
export PULSO_PYTHON="${PULSO_PYTHON:-${PULSO_DATA_ROOT}/venvs/litert-lm-py310/bin/python}"
export PULSO_GEMMA_MODEL="${PULSO_GEMMA_MODEL:-${PULSO_DATA_ROOT}/models/${PULSO_GEMMA_FILENAME}}"
export PULSO_GEMMA_MODEL_SHA256="${PULSO_GEMMA_MODEL_SHA256:-${PULSO_GEMMA_SHA256}}"
export PULSO_LITERT_BACKEND="${PULSO_LITERT_BACKEND:-gpu}"

if [[ -f "${PULSO_STATE_ROOT}/artifacts.env" ]]; then
  # shellcheck disable=SC1090
  source "${PULSO_STATE_ROOT}/artifacts.env"
fi

for _pulso_path in \
  "${PULSO_DATA_ROOT}/tools/node-current/bin" \
  "${ANDROID_HOME}/platform-tools" \
  "${ANDROID_HOME}/cmdline-tools/latest/bin"; do
  case ":${PATH}:" in *":${_pulso_path}:"*) ;; *) PATH="${_pulso_path}:${PATH}" ;; esac
done
export PATH

_pulso_source_setup() {
  local setup="$1" restore_nounset=0
  [[ -f "${setup}" ]] || return 0
  [[ $- == *u* ]] && restore_nounset=1 && set +u
  # shellcheck disable=SC1090
  source "${setup}"
  [[ "${restore_nounset}" == "1" ]] && set -u
}
_pulso_source_setup /opt/ros/humble/setup.bash
_pulso_source_setup "${PULSO_PROJECT_ROOT}/sim/ros2_ws/install/setup.bash"
unset -f _pulso_source_setup
unset _pulso_path _pulso_env_dir _pulso_project_root
return 0
