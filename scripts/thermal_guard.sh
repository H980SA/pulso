#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
interval_s="${PULSO_THERMAL_SAMPLE_S:-2}"
# Ryzen 7 5700G has a 95 C Tjmax.  A short inference spike below it is not the
# same as sustained heat, so the demo profile permits brief 90--92 C bursts
# while retaining a one-degree emergency margin and a bounded hot window.
sustained_c="${PULSO_THERMAL_SUSTAINED_C:-92.0}"
hard_c="${PULSO_THERMAL_HARD_C:-94.0}"
sustained_samples="${PULSO_THERMAL_SUSTAINED_SAMPLES:-5}"
log_path="${PULSO_THERMAL_LOG:-${project_root}/sim/logs/thermal/guard-$(date -u +%Y%m%dT%H%M%SZ).log}"
hot_samples=0

mkdir -p "$(dirname "${log_path}")"

temperature_c() {
  sensors 2>/dev/null | awk '/Tctl:/ {gsub(/[+°C]/, "", $2); print $2; exit}'
}

at_or_above() {
  awk -v current="$1" -v limit="$2" 'BEGIN {exit !(current >= limit)}'
}

stop_workload() {
  local reason="$1"
  printf '%s THERMAL_STOP reason=%s\n' "$(date -u +%FT%TZ)" "${reason}" | tee -a "${log_path}"
  tmux send-keys -t pulso-demo:0.0 C-c 2>/dev/null || true
  "${project_root}/apps/pulso-brain-host/stop.sh" >>"${log_path}" 2>&1 || true
}

printf '%s THERMAL_GUARD sustained=%s hard=%s samples=%s interval=%ss\n' \
  "$(date -u +%FT%TZ)" "${sustained_c}" "${hard_c}" "${sustained_samples}" "${interval_s}" \
  | tee -a "${log_path}"

while true; do
  current_c="$(temperature_c)"
  if [[ -z "${current_c}" ]]; then
    printf '%s SENSOR_ERROR no Tctl reading\n' "$(date -u +%FT%TZ)" | tee -a "${log_path}" >&2
    exit 2
  fi
  printf '%s Tctl=%sC\n' "$(date -u +%FT%TZ)" "${current_c}" >>"${log_path}"

  if at_or_above "${current_c}" "${hard_c}"; then
    stop_workload "hard_limit_${current_c}C"
    exit 75
  fi
  if at_or_above "${current_c}" "${sustained_c}"; then
    hot_samples=$((hot_samples + 1))
  else
    hot_samples=0
  fi
  if (( hot_samples >= sustained_samples )); then
    stop_workload "sustained_${current_c}C_${hot_samples}_samples"
    exit 75
  fi
  sleep "${interval_s}"
done
