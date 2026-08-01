#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
robot_host="${1:-exomy@10.245.145.36}"
ssh_key="${PULSO_ROBOT_SSH_KEY:-${HOME}/.ssh/pulso_robot_ed25519}"
remote_package="/opt/pulso-rover/venv/lib/python3.11/site-packages/pulso_rover"
staging="/tmp/pulso-gateway-overlay-${USER:-operator}"
expected_config="1c9ec3a0c921ef6fb0c4a954ce4c137bda7d71c359321e0be6d7ca48455e318f"
expected_service="92f0c388496a66943c6bc0dea6088767c5b19379727488ca1f7c55428eb10e3e"
overlay="${repo_root}/infra/exomy/gateway-overlay/pulso_rover"

[[ -r "${ssh_key}" ]] || { echo "SSH key not readable: ${ssh_key}" >&2; exit 1; }
for file in config.py service.py; do
  [[ -f "${overlay}/${file}" ]] || { echo "Overlay missing: ${overlay}/${file}" >&2; exit 1; }
done

ssh_args=(-i "${ssh_key}" -o BatchMode=yes -o ConnectTimeout=5)
current="$(ssh "${ssh_args[@]}" "${robot_host}" \
  "sha256sum '${remote_package}/config.py' '${remote_package}/service.py'" | awk '{print $1}' | paste -sd: -)"
overlay_hashes="$(sha256sum "${overlay}/config.py" "${overlay}/service.py" | awk '{print $1}' | paste -sd: -)"
case "${current}" in
  "${expected_config}:${expected_service}"|"${overlay_hashes}") ;;
  *)
    echo "Refusing to overwrite an unknown gateway source revision: ${current}" >&2
    exit 1
    ;;
esac

ssh "${ssh_args[@]}" "${robot_host}" "rm -rf '${staging}' && mkdir -m 0700 '${staging}'"
scp "${ssh_args[@]}" -q "${overlay}/config.py" "${overlay}/service.py" "${robot_host}:${staging}/"
ssh "${ssh_args[@]}" "${robot_host}" "STAGING='${staging}' PACKAGE='${remote_package}' bash -s" <<'REMOTE'
set -euo pipefail
backup="/opt/pulso-rover/backups/gateway-$(date -u +%Y%m%dT%H%M%SZ)"
sudo -n install -d -m 0700 -o root -g root "${backup}"
sudo -n install -m 0600 -o root -g root "${PACKAGE}/config.py" "${backup}/config.py"
sudo -n install -m 0600 -o root -g root "${PACKAGE}/service.py" "${backup}/service.py"
restore() {
  sudo -n install -m 0644 -o root -g root "${backup}/config.py" "${PACKAGE}/config.py"
  sudo -n install -m 0644 -o root -g root "${backup}/service.py" "${PACKAGE}/service.py"
  sudo -n systemctl restart pulso-rover-gateway.service || true
}
trap restore ERR
sudo -n install -m 0644 -o root -g root "${STAGING}/config.py" "${PACKAGE}/config.py"
sudo -n install -m 0644 -o root -g root "${STAGING}/service.py" "${PACKAGE}/service.py"
sudo -n /opt/pulso-rover/venv/bin/python -m py_compile "${PACKAGE}/config.py" "${PACKAGE}/service.py"
sudo -n systemctl restart pulso-rover-gateway.service
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8765/health | grep -q '"mode":"SHADOW"'; then
    trap - ERR
    rm -rf "${STAGING}"
    echo "gateway-overlay: deployed, service healthy, stage remains SHADOW"
    exit 0
  fi
  sleep 0.25
done
echo "Gateway did not return healthy SHADOW state" >&2
exit 1
REMOTE
