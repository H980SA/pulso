#!/usr/bin/env bash
set -euo pipefail

robot_host="${1:-exomy@10.245.145.36}"
ssh_key="${PULSO_ROBOT_SSH_KEY:-${HOME}/.ssh/pulso_robot_ed25519}"
ssh -i "${ssh_key}" -o BatchMode=yes -o ConnectTimeout=5 "${robot_host}" 'bash -s' <<'REMOTE'
set -euo pipefail
token="$(sudo -n cat /etc/pulso-rover/api-token)"
revision="$(curl -fsS -H "Authorization: Bearer ${token}" http://127.0.0.1:8765/v1/world-state | \
  /opt/pulso-rover/venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["world_revision"])')"
curl -fsS -X POST -H "Authorization: Bearer ${token}" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: disarm-$(date +%s%N)" \
  -d "{\"command_type\":\"STOP\",\"expected_world_revision\":${revision},\"speed_profile\":\"CREEP\",\"reason\":\"operator disarm script\",\"requested_by\":\"field-operator\"}" \
  http://127.0.0.1:8765/v1/commands >/dev/null || true
sudo -n rm -f /etc/systemd/system/pulso-rover-gateway.service.d/ground.conf
sudo -n systemctl daemon-reload
sudo -n systemctl restart pulso-rover-gateway.service
curl -fsS http://127.0.0.1:8765/health | grep -q '"mode":"SHADOW"'
echo "gateway-ground: STOP attempted, ground override removed, SHADOW restored"
REMOTE
