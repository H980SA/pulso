#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${PULSO_BRAIN_RUNTIME_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/pulso/brain-host}"
PID_FILE="$RUNTIME_DIR/brain-host.pid"

owns_process() {
  local pid="$1"
  local run_id="$2"
  local command
  kill -0 "$pid" 2>/dev/null || return 1
  command="$(ps -ww -p "$pid" -o command= 2>/dev/null)" || return 1
  [[ "$command" == *"supervise.sh"* && "$command" == *"$run_id"* ]]
}

if [[ ! -f "$PID_FILE" ]]; then
  echo "PULSO brain host is not running."
  exit 0
fi
read -r PID RUN_ID < "$PID_FILE" || true
if [[ -z "${PID:-}" || -z "${RUN_ID:-}" ]] || ! owns_process "$PID" "$RUN_ID"; then
  rm -f "$PID_FILE"
  echo "Removed stale PID file without signaling an unrelated process."
  exit 0
fi

kill -TERM "$PID"
for _ in {1..30}; do
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "PULSO brain host stopped."
    exit 0
  fi
  sleep 0.2
done
echo "PULSO brain host did not stop within 6 seconds; PID $PID remains." >&2
exit 1
