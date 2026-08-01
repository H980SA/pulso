#!/usr/bin/env bash
set -euo pipefail

readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REAL_WEB_PORT=4173
readonly SIM_WEB_PORT=4174
readonly REAL_BRIDGE_PORT=9091
readonly SIM_BRIDGE_PORT=9092
readonly REAL_ROS_DOMAIN=42
readonly SIM_ROS_DOMAIN=43
# shellcheck disable=SC1091
source "${PROJECT_ROOT}/infra/ubuntu/pulso-env.sh"
# shellcheck disable=SC1091
source "${PROJECT_ROOT}/scripts/lib/pulso_processes.sh"

usage() {
  cat <<'EOF'
Uso: ./pulso <comando>

  install          instala Ubuntu 22.04 + Android/ROS/Gazebo/Blender/runtimes
  doctor           comprueba la estación y los artefactos fijados
  sim [--headless] [--host-brain]
                   arranca Gazebo, RViz, rosbridge y Mission Control; el S25
                   es el único cerebro por defecto
  real [--dry-run] prepara S25 + web + rosbridge; Zeus nunca recibe movimiento
  stop             detiene ambos perfiles y retira adb reverse

Perfiles aislados:
  REAL  http://127.0.0.1:4173  · rosbridge 9091 · ROS_DOMAIN_ID 42
  SIM   http://127.0.0.1:4174  · rosbridge 9092 · ROS_DOMAIN_ID 43

Variables: PULSO_DATA_ROOT, PULSO_STATE_ROOT, PULSO_GEMMA_MODEL, PULSO_APK.
Docker es opcional: PULSO_INSTALL_DOCKER=1 ./pulso install
EOF
}

require_ubuntu() {
  [[ -r /etc/os-release ]] || { echo "Este comando requiere Ubuntu 22.04." >&2; exit 2; }
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID:-}" == ubuntu && "${VERSION_CODENAME:-}" == jammy ]] || {
    echo "Este comando requiere Ubuntu 22.04 Jammy." >&2
    exit 2
  }
}

verify_file() {
  local label="$1" path="$2" expected_sha="$3" expected_bytes="$4"
  [[ -f "${path}" ]] || { echo "ERROR ${label} ausente: ${path}" >&2; return 1; }
  local actual_sha actual_bytes
  actual_sha="$(sha256sum "${path}" | awk '{print $1}')"
  actual_bytes="$(wc -c < "${path}" | tr -d ' ')"
  [[ "${actual_sha}" == "${expected_sha}" && "${actual_bytes}" == "${expected_bytes}" ]] || {
    printf 'ERROR %s no coincide: sha=%s bytes=%s\n' "${label}" "${actual_sha}" "${actual_bytes}" >&2
    return 1
  }
  printf 'Verificado %s: %s (%s bytes).\n' "${label}" "${actual_sha}" "${actual_bytes}"
}

start_web() {
  local profile="$1" port="$2" service="web-$1" field_mode=0
  [[ "${profile}" == "real" ]] && field_mode=1
  if start_service "${service}" env \
      PULSO_FIELD_MODE="${field_mode}" \
      PULSO_MISSION_STATE_DIR="${PULSO_STATE_ROOT}/mission-control/${profile}" \
      "${PROJECT_ROOT}/apps/pulso-mission-control/run.sh" "${port}"; then
    STARTED_SERVICES+=("${service}")
  else
    [[ "$?" == 10 ]] || return 1
  fi
  wait_port 127.0.0.1 "${port}" 15 "Mission Control ${profile^^}"
}

cleanup_new_services() {
  local index
  for ((index = ${#STARTED_SERVICES[@]} - 1; index >= 0; index--)); do
    stop_service "${STARTED_SERVICES[index]}" || true
  done
}

run_sim() {
  require_ubuntu
  local rviz=true headless=false host_brain=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --headless) rviz=false; headless=true ;;
      --host-brain) host_brain=true ;;
      *) usage >&2; return 2 ;;
    esac
    shift
  done
  verify_file "Gemma 4 E4B" "${PULSO_GEMMA_MODEL}" \
    "${PULSO_GEMMA_SHA256}" "${PULSO_GEMMA_BYTES}"
  if [[ "${host_brain}" == true && ! -x "${PULSO_PYTHON}" ]]; then
    echo "ERROR runtime Gemma ausente; ejecute ./pulso install." >&2
    return 1
  fi
  STARTED_SERVICES=()
  trap cleanup_new_services ERR
  trap 'cleanup_new_services; exit 130' INT
  trap 'cleanup_new_services; exit 143' TERM
  if start_service sim env ROS_DOMAIN_ID="${SIM_ROS_DOMAIN}" \
      "${PROJECT_ROOT}/scripts/run_sim.sh" "rviz:=${rviz}" "headless:=${headless}" \
      "hil_port:=${SIM_BRIDGE_PORT}"; then
    STARTED_SERVICES+=(sim)
  else
    [[ "$?" == 10 ]] || return 1
  fi
  wait_port 127.0.0.1 "${SIM_BRIDGE_PORT}" "${PULSO_START_TIMEOUT_S:-90}" "rosbridge SIM"
  start_web sim "${SIM_WEB_PORT}"
  if [[ "${host_brain}" == true ]]; then
    if start_service brain-sim env \
        ROS_DOMAIN_ID="${SIM_ROS_DOMAIN}" \
        PULSO_ROSBRIDGE_URL="ws://127.0.0.1:${SIM_BRIDGE_PORT}" \
        "${PROJECT_ROOT}/apps/pulso-brain-host/run.sh"; then
      STARTED_SERVICES+=(brain-sim)
    else
      [[ "$?" == 10 ]] || return 1
    fi
    wait_log_pattern brain-sim "Gemma engine warm" "${PULSO_GEMMA_START_TIMEOUT_S:-60}" \
      "Gemma 4 E4B host"
  fi
  trap - ERR INT TERM
  printf '\nSIM LISTA · http://127.0.0.1:%s/?profile=sim&bridge=ws://127.0.0.1:%s\n' \
    "${SIM_WEB_PORT}" "${SIM_BRIDGE_PORT}"
  if [[ "${host_brain}" == true ]]; then
    echo "Cerebro activo: host Ubuntu (--host-brain). No conecte el agente del S25 a la vez."
  else
    echo "Cerebro activo esperado: S25. Abra Pulso y pulse CONECTAR GAZEBO."
  fi
  printf 'Logs: %s\nDetener: ./pulso stop\n' "${log_dir}"
}

adb_identity() {
  local serial_count
  mapfile -t ADB_SERIALS < <(adb devices | awk 'NR>1 && $2=="device" {print $1}')
  serial_count="${#ADB_SERIALS[@]}"
  [[ "${serial_count}" == 1 ]] || {
    echo "ERROR se requiere exactamente un Android autorizado; encontrados ${serial_count}." >&2
    adb devices -l >&2
    return 1
  }
  ADB_SERIAL="${ADB_SERIALS[0]}"
  ADB=(adb -s "${ADB_SERIAL}")
  local manufacturer model regex
  manufacturer="$("${ADB[@]}" shell getprop ro.product.manufacturer | tr -d '\r')"
  model="$("${ADB[@]}" shell getprop ro.product.model | tr -d '\r')"
  regex="${PULSO_S25_MODEL_REGEX:-SM-S93[168]|S25}"
  [[ "${manufacturer}" =~ [Ss]amsung && "${model}" =~ ${regex} ]] || {
    printf 'ERROR dispositivo no reconocido como Samsung S25: %s %s\n' "${manufacturer}" "${model}" >&2
    return 1
  }
  printf 'S25 autorizado: serial=%s modelo=%s.\n' "${ADB_SERIAL}" "${model}"
}

device_physical_preflight() {
  local features available_kib required_kib
  "${ADB[@]}" shell pm path com.google.ar.core >/dev/null 2>&1 || {
    echo "ERROR Google Play Services for AR (ARCore) no está instalado/actualizado en el S25." >&2
    return 1
  }
  features="$("${ADB[@]}" shell pm list features | tr -d '\r')"
  for feature in android.hardware.camera.any android.hardware.camera.flash \
    android.hardware.sensor.accelerometer android.hardware.sensor.gyroscope; do
    grep -Fq "feature:${feature}" <<< "${features}" || {
      printf 'ERROR capacidad requerida ausente en S25: %s\n' "${feature}" >&2
      return 1
    }
  done
  available_kib="$("${ADB[@]}" shell df -Pk /storage/emulated/0 2>/dev/null | awk 'END {print $4}' | tr -d '\r')"
  [[ "${available_kib}" =~ ^[0-9]+$ ]] || {
    echo "ERROR no se pudo medir espacio libre del almacenamiento compartido del S25." >&2
    return 1
  }
  required_kib=$(( (PULSO_GEMMA_BYTES + 1073741824) / 1024 ))
  (( available_kib >= required_kib )) || {
    printf 'ERROR espacio insuficiente en S25: disponibles=%s KiB requeridos=%s KiB.\n' \
      "${available_kib}" "${required_kib}" >&2
    return 1
  }
  printf 'Preflight físico: ARCore, sensores y %s MiB libres verificados.\n' "$((available_kib / 1024))"
}

device_diagnostics() {
  local report_dir report
  report_dir="${PULSO_STATE_ROOT}/diagnostics"
  mkdir -p "${report_dir}"
  report="${report_dir}/s25-$(date -u +%Y%m%dT%H%M%SZ).log"
  {
    echo "PULSO S25 PREFLIGHT (solo lectura)"
    "${ADB[@]}" shell getprop ro.product.model
    "${ADB[@]}" shell getprop ro.build.version.release
    "${ADB[@]}" shell pm list features | grep -E 'camera|flash|sensor.accelerometer|sensor.gyroscope' || true
    "${ADB[@]}" shell pm list packages com.google.ar.core || true
    "${ADB[@]}" shell dumpsys package com.pulso.app | grep -E 'versionName=|versionCode=|android.permission.(CAMERA|RECORD_AUDIO)' || true
    echo "ANDROID_REAL=IMPLEMENTADO_NO_EJECUTADO: este diagnóstico no abre Camera/ARCore Depth/VIO/IMU/torch."
    echo "ZEUS=DRY_RUN: Arduino UNO + shield + ESP32-CAM; no se envió ningún comando de motor."
  } | tee "${report}"
  printf 'Diagnóstico: %s\n' "${report}"
}

cleanup_real_failure() {
  cleanup_new_services
  if declare -p ADB >/dev/null 2>&1 && [[ "${#ADB[@]}" == 3 ]]; then
    "${ADB[@]}" shell am force-stop com.pulso.app >/dev/null 2>&1 || true
    "${ADB[@]}" reverse --remove tcp:9091 >/dev/null 2>&1 || true
  fi
}

run_real() {
  require_ubuntu
  local dry_run=0 apk_path device_model_path device_sha
  if [[ "${1:-}" == "--dry-run" ]]; then dry_run=1; shift; fi
  [[ $# -eq 0 ]] || { usage >&2; return 2; }
  apk_path="${PULSO_APK:-${PROJECT_ROOT}/dist/${PULSO_APK_FILENAME}}"
  verify_file "APK Pulso" "${apk_path}" \
    "${PULSO_LOCAL_APK_SHA256:-${PULSO_APK_SHA256}}" \
    "${PULSO_LOCAL_APK_BYTES:-${PULSO_APK_BYTES}}"
  verify_file "Gemma 4 E4B" "${PULSO_GEMMA_MODEL}" \
    "${PULSO_GEMMA_SHA256}" "${PULSO_GEMMA_BYTES}"
  adb_identity
  device_physical_preflight
  if (( dry_run == 1 )); then
    device_diagnostics
    return
  fi

  STARTED_SERVICES=()
  trap cleanup_real_failure ERR
  trap 'cleanup_real_failure; exit 130' INT
  trap 'cleanup_real_failure; exit 143' TERM
  if start_service bridge-real env \
      ROS_DOMAIN_ID="${REAL_ROS_DOMAIN}" \
      PULSO_ROSBRIDGE_PORT="${REAL_BRIDGE_PORT}" \
      "${PROJECT_ROOT}/infra/ubuntu/run_real_bridge.sh"; then
    STARTED_SERVICES+=(bridge-real)
  else
    [[ "$?" == 10 ]] || return 1
  fi
  wait_port 127.0.0.1 "${REAL_BRIDGE_PORT}" 30 "rosbridge REAL"
  start_web real "${REAL_WEB_PORT}"

  "${ADB[@]}" reverse "tcp:${REAL_BRIDGE_PORT}" "tcp:${REAL_BRIDGE_PORT}"
  "${ADB[@]}" install -r -t "${apk_path}"
  ANDROID_SERIAL="${ADB_SERIAL}" \
    "${PROJECT_ROOT}/scripts/android/push_model.sh" "${PULSO_GEMMA_MODEL}"
  "${ADB[@]}" shell pm grant com.pulso.app android.permission.CAMERA
  "${ADB[@]}" shell pm grant com.pulso.app android.permission.RECORD_AUDIO
  "${ADB[@]}" shell am force-stop com.pulso.app
  "${ADB[@]}" shell am start -n com.pulso.app/.MainActivity >/dev/null

  device_model_path="/storage/emulated/0/Android/data/com.pulso.app/files/models/${PULSO_GEMMA_FILENAME}"
  device_sha="$("${ADB[@]}" shell sha256sum "${device_model_path}" | tr -d '\r' | awk '{print $1}')"
  [[ "${device_sha}" == "${PULSO_GEMMA_SHA256}" ]] || {
    echo "ERROR hash E4B en S25 no coincide." >&2
    return 1
  }
  device_diagnostics
  trap - ERR INT TERM
  printf '\nREAL PREPARADO · http://127.0.0.1:%s/?profile=real&bridge=ws://127.0.0.1:%s\n' \
    "${REAL_WEB_PORT}" "${REAL_BRIDGE_PORT}"
  echo "S25 listo en modo físico local; la telemetría sale por adb reverse a Mission Control."
  echo "ZEUS: transporte DRY_RUN por defecto. No se envía movimiento hasta armarlo de forma explícita y supervisada."
}

run_stop() {
  local result=0 name
  for name in brain-sim web-real web-sim bridge-real sim brain web rosbridge; do
    stop_service "${name}" || result=1
  done
  if command -v adb >/dev/null 2>&1; then
    mapfile -t stop_serials < <(adb devices | awk 'NR>1 && $2=="device" {print $1}')
    if [[ "${#stop_serials[@]}" == 1 ]]; then
      adb -s "${stop_serials[0]}" shell am force-stop com.pulso.app >/dev/null 2>&1 || true
      adb -s "${stop_serials[0]}" reverse --remove "tcp:${REAL_BRIDGE_PORT}" >/dev/null 2>&1 || true
      echo "App Pulso detenida y adb reverse retirado."
    fi
  fi
  return "${result}"
}

command_name="${1:-help}"
shift || true
case "${command_name}" in
  install) require_ubuntu; exec "${PROJECT_ROOT}/infra/ubuntu/bootstrap.sh" "$@" ;;
  doctor) exec "${PROJECT_ROOT}/infra/ubuntu/verify.sh" "$@" ;;
  sim) run_sim "$@" ;;
  real) run_real "$@" ;;
  stop) [[ $# -eq 0 ]] || { usage >&2; exit 2; }; run_stop ;;
  help|-h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
