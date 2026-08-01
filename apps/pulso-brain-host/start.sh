#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${PULSO_BRAIN_RUNTIME_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/pulso/brain-host}"
PID_FILE="$RUNTIME_DIR/brain-host.pid"
EXIT_FILE="$RUNTIME_DIR/brain-host.exit"
LOG_FILE="$RUNTIME_DIR/brain-host.log"
STARTUP_GRACE_S="${PULSO_STARTUP_GRACE_S:-10}"
mkdir -p "$RUNTIME_DIR"

owns_process() {
  local pid="$1"
  local run_id="$2"
  local command
  kill -0 "$pid" 2>/dev/null || return 1
  command="$(ps -ww -p "$pid" -o command= 2>/dev/null)" || return 1
  [[ "$command" == *"supervise.sh"* && "$command" == *"$run_id"* ]]
}

if [[ -f "$PID_FILE" ]]; then
  read -r existing_pid existing_run_id < "$PID_FILE" || true
  if [[ -n "${existing_pid:-}" && -n "${existing_run_id:-}" ]] \
    && owns_process "$existing_pid" "$existing_run_id"; then
    echo "PULSO brain host is already supervised with PID $existing_pid" >&2
    exit 3
  fi
  rm -f "$PID_FILE"
fi

if [[ ! "$STARTUP_GRACE_S" =~ ^[0-9]+$ ]]; then
  echo "PULSO_STARTUP_GRACE_S must be a non-negative integer" >&2
  exit 2
fi

run_id="$(date -u '+%Y%m%dT%H%M%SZ')-$$-$RANDOM"
rm -f "$EXIT_FILE"
nohup "$APP_DIR/supervise.sh" "$RUNTIME_DIR" "$run_id" "$@" \
  >> "$LOG_FILE" 2>&1 < /dev/null &
supervisor_pid=$!
temporary_pid_file="$PID_FILE.tmp.$$"
printf '%s %s\n' "$supervisor_pid" "$run_id" > "$temporary_pid_file"
mv -f "$temporary_pid_file" "$PID_FILE"

for ((tick = 0; tick < STARTUP_GRACE_S * 10; tick++)); do
  if ! owns_process "$supervisor_pid" "$run_id"; then
    rm -f "$PID_FILE"
    echo "PULSO brain host exited during its ${STARTUP_GRACE_S}s startup check." >&2
    if [[ -f "$EXIT_FILE" ]]; then
      sed 's/^/  /' "$EXIT_FILE" >&2
    fi
    echo "Log: $LOG_FILE" >&2
    exit 1
  fi
  sleep 0.1
done

echo "PULSO brain host process survived the ${STARTUP_GRACE_S}s startup check (run_id=$run_id)."
echo "This confirms process survival only; inspect readiness and inference evidence in $LOG_FILE"
