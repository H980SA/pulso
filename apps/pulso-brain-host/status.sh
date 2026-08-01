#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${PULSO_BRAIN_RUNTIME_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/pulso/brain-host}"
PID_FILE="$RUNTIME_DIR/brain-host.pid"
EXIT_FILE="$RUNTIME_DIR/brain-host.exit"
LOG_FILE="$RUNTIME_DIR/brain-host.log"

if [[ -f "$PID_FILE" ]]; then
  read -r pid run_id < "$PID_FILE" || true
  command="$(ps -ww -p "${pid:-missing}" -o command= 2>/dev/null || true)"
  if [[ -n "${pid:-}" && -n "${run_id:-}" \
    && "$command" == *"supervise.sh"* && "$command" == *"$run_id"* ]]; then
    echo "process=running pid=$pid run_id=$run_id"
    echo "health=unknown (process state is not rosbridge or inference evidence)"
    echo "log=$LOG_FILE"
    exit 0
  fi
  echo "process=stopped stale_pid_file=$PID_FILE"
else
  echo "process=stopped"
fi

if [[ -f "$EXIT_FILE" ]]; then
  sed 's/^/last_/' "$EXIT_FILE"
fi
echo "log=$LOG_FILE"
exit 1
