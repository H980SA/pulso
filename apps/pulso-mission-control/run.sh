#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
port="${1:-4173}"

# The operator never copies a bearer token into the browser. In field mode the
# local server retrieves it over the robot's SSH control plane and keeps it only
# in this process so PARAR TODO can latch the gateway even if the phone stalls.
if [[ "${PULSO_FIELD_MODE:-0}" == "1" && -z "${PULSO_ROVER_TOKEN:-}" ]]; then
  robot_host="${PULSO_ROBOT_SSH_TARGET:-exomy@10.245.145.36}"
  ssh_key="${PULSO_ROBOT_SSH_KEY:-${HOME}/.ssh/pulso_robot_ed25519}"
  if [[ -f "${ssh_key}" ]]; then
    rover_token="$(ssh -i "${ssh_key}" -o BatchMode=yes -o ConnectTimeout=3 "${robot_host}" \
      'sudo -n cat /etc/pulso-rover/api-token' 2>/dev/null || true)"
    if [[ -n "${rover_token}" ]]; then
      export PULSO_ROVER_TOKEN="${rover_token}"
    elif [[ "${PULSO_REQUIRE_ROVER:-0}" == "1" ]]; then
      echo "Field mode requires an SSH-retrievable rover credential." >&2
      exit 1
    else
      echo "Warning: rover credential unavailable; direct gateway e-stop is not armed." >&2
    fi
  elif [[ "${PULSO_REQUIRE_ROVER:-0}" == "1" ]]; then
    echo "Field mode requires SSH key ${ssh_key}." >&2
    exit 1
  else
    echo "Warning: rover SSH key unavailable; direct gateway e-stop is not armed." >&2
  fi
fi
export PULSO_ROVER_URL="${PULSO_ROVER_URL:-http://10.245.145.36:8765}"

exec python3 "$script_dir/serve.py" --port "$port"
