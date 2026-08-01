#!/usr/bin/env bash

runtime_dir="${PULSO_STATE_ROOT}/orchestrator"
pid_dir="${runtime_dir}/pids"
log_dir="${runtime_dir}/logs"
mkdir -p "${pid_dir}" "${log_dir}"

service_pid_file() { printf '%s/%s.pid\n' "${pid_dir}" "$1"; }
service_log_file() { printf '%s/%s.log\n' "${log_dir}" "$1"; }

service_running() {
  local name="$1" pid_file pid token
  pid_file="$(service_pid_file "${name}")"
  [[ -r "${pid_file}" ]] || return 1
  read -r pid token < "${pid_file}" || return 1
  [[ "${pid:-}" =~ ^[0-9]+$ && -n "${token:-}" ]] || return 1
  kill -0 "${pid}" 2>/dev/null || return 1
  [[ -r "/proc/${pid}/environ" ]] || return 1
  tr '\0' '\n' < "/proc/${pid}/environ" | grep -Fxq "PULSO_RUN_TOKEN=${token}"
}

start_service() {
  local name="$1"
  shift
  local pid_file log_file token pid tick
  pid_file="$(service_pid_file "${name}")"
  log_file="$(service_log_file "${name}")"
  if service_running "${name}"; then
    read -r pid _ < "${pid_file}"
    printf '%s ya está activo (PID %s). Log: %s\n' "${name}" "${pid}" "${log_file}"
    return 10
  fi
  rm -f "${pid_file}"
  token="${name}-$(date -u +%Y%m%dT%H%M%SZ)-$$-${RANDOM}"
  if [[ -s "${log_file}" ]]; then
    mv "${log_file}" "${log_file%.log}.${token}.log"
  fi
  PULSO_RUN_TOKEN="${token}" setsid "$@" >> "${log_file}" 2>&1 < /dev/null &
  pid=$!
  printf '%s %s\n' "${pid}" "${token}" > "${pid_file}.tmp.$$"
  mv -f "${pid_file}.tmp.$$" "${pid_file}"
  for tick in {1..20}; do
    if service_running "${name}"; then
      printf '%s iniciado (PID %s). Log: %s\n' "${name}" "${pid}" "${log_file}"
      return 0
    fi
    sleep 0.1
  done
  rm -f "${pid_file}"
  printf 'ERROR %s terminó al arrancar. Log: %s\n' "${name}" "${log_file}" >&2
  tail -n 30 "${log_file}" >&2 || true
  return 1
}

stop_service() {
  local name="$1" pid_file pid token tick pgid
  pid_file="$(service_pid_file "${name}")"
  if ! service_running "${name}"; then
    rm -f "${pid_file}"
    printf '%s ya estaba detenido.\n' "${name}"
    return 0
  fi
  read -r pid token < "${pid_file}"
  pgid="$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ')"
  if [[ "${pgid}" == "${pid}" ]]; then
    kill -TERM -- "-${pid}" 2>/dev/null || true
  else
    kill -TERM "${pid}" 2>/dev/null || true
  fi
  for tick in {1..50}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      rm -f "${pid_file}"
      printf '%s detenido.\n' "${name}"
      return 0
    fi
    sleep 0.2
  done
  printf 'ERROR %s no terminó en 10 s; PID %s permanece y no se forzó SIGKILL.\n' \
    "${name}" "${pid}" >&2
  return 1
}

wait_port() {
  local host="$1" port="$2" timeout_s="$3" label="$4" tick
  for ((tick = 0; tick < timeout_s * 2; tick++)); do
    if nc -z "${host}" "${port}" >/dev/null 2>&1; then
      printf '%s listo en %s:%s.\n' "${label}" "${host}" "${port}"
      return 0
    fi
    sleep 0.5
  done
  printf 'ERROR timeout esperando %s en %s:%s.\n' "${label}" "${host}" "${port}" >&2
  return 1
}

wait_log_pattern() {
  local name="$1" pattern="$2" timeout_s="$3" label="$4" tick log_file
  log_file="$(service_log_file "${name}")"
  for ((tick = 0; tick < timeout_s * 2; tick++)); do
    if grep -Fq "${pattern}" "${log_file}" 2>/dev/null; then
      printf '%s listo.\n' "${label}"
      return 0
    fi
    service_running "${name}" || {
      printf 'ERROR %s terminó antes de estar listo. Log: %s\n' "${label}" "${log_file}" >&2
      tail -n 30 "${log_file}" >&2 || true
      return 1
    }
    sleep 0.5
  done
  printf 'ERROR timeout esperando %s. Log: %s\n' "${label}" "${log_file}" >&2
  return 1
}
