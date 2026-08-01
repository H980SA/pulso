#!/usr/bin/env bash
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$#" -lt 2 ]]; then
  echo "Usage: supervise.sh RUNTIME_DIR RUN_ID [brain arguments...]" >&2
  exit 2
fi
RUNTIME_DIR="$1"
RUN_ID="$2"
shift 2
PID_FILE="$RUNTIME_DIR/brain-host.pid"
EXIT_FILE="$RUNTIME_DIR/brain-host.exit"
RUNNER="${PULSO_BRAIN_RUNNER:-$APP_DIR/run.sh}"
CHILD_PID=""

timestamp() {
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

record_exit() {
  local status="$1"
  local signal_number=0
  if (( status > 128 )); then
    signal_number=$((status - 128))
  fi
  local temporary="$EXIT_FILE.tmp.$$"
  {
    printf 'run_id=%s\n' "$RUN_ID"
    printf 'supervisor_pid=%s\n' "$$"
    printf 'exited_at=%s\n' "$(timestamp)"
    printf 'exit_code=%s\n' "$status"
    printf 'signal=%s\n' "$signal_number"
  } > "$temporary"
  mv -f "$temporary" "$EXIT_FILE"

  if [[ -f "$PID_FILE" ]]; then
    read -r recorded_pid recorded_run_id < "$PID_FILE" || true
    if [[ "$recorded_pid" == "$$" && "$recorded_run_id" == "$RUN_ID" ]]; then
      rm -f "$PID_FILE"
    fi
  fi
  printf '%s PULSO brain host exited: run_id=%s exit_code=%s signal=%s\n' \
    "$(timestamp)" "$RUN_ID" "$status" "$signal_number" >&2
}

forward_signal() {
  local signal_name="$1"
  if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
    kill -s "$signal_name" "$CHILD_PID" 2>/dev/null || true
  fi
}

trap 'forward_signal TERM' TERM
trap 'forward_signal INT' INT

printf '%s PULSO brain host launch: run_id=%s supervisor_pid=%s\n' \
  "$(timestamp)" "$RUN_ID" "$$" >&2
"$RUNNER" "$@" &
CHILD_PID=$!

status=0
while true; do
  wait "$CHILD_PID"
  status=$?
  if ! kill -0 "$CHILD_PID" 2>/dev/null; then
    break
  fi
done

record_exit "$status"
exit "$status"
