#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--confirm-operator-at-power-cutoff" ]]; then
  echo "Usage: $0 --confirm-operator-at-power-cutoff [exomy@host]" >&2
  exit 2
fi
robot_host="${2:-exomy@10.245.145.36}"
ssh_key="${PULSO_ROBOT_SSH_KEY:-${HOME}/.ssh/pulso_robot_ed25519}"

ssh -i "${ssh_key}" -o BatchMode=yes -o ConnectTimeout=5 "${robot_host}" 'bash -s' <<'REMOTE'
set -euo pipefail
ss -ltn | grep -q '127.0.0.1:8765' && {
  echo "Gateway is loopback-only; the S25 cannot reach it." >&2
  exit 1
}
sudo -n iptables -C DOCKER-USER -p tcp --dport 9090 '!' -s 127.0.0.1 -j DROP 2>/dev/null || \
  sudo -n iptables -I DOCKER-USER 1 -p tcp --dport 9090 '!' -s 127.0.0.1 -j DROP
dropin=/etc/systemd/system/pulso-rover-gateway.service.d/ground.conf
sudo -n install -d -m 0755 /etc/systemd/system/pulso-rover-gateway.service.d
tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT
printf '%s\n' \
  '[Service]' \
  'Environment=PULSO_STAGE=GROUND' \
  'Environment=PULSO_ALLOW_ACTUATION=true' \
  'Environment=PULSO_EXCLUSIVE_CONTROL_CONFIRMED=true' \
  'Environment=PULSO_GROUND_SUPERVISED_CONFIRMED=true' \
  'Environment=PULSO_MAX_DURATION_MS=150' >"${tmp}"
sudo -n install -m 0644 -o root -g root "${tmp}" "${dropin}"
sudo -n systemctl daemon-reload
if ! sudo -n systemctl restart pulso-rover-gateway.service; then
  sudo -n rm -f "${dropin}"
  sudo -n systemctl daemon-reload
  sudo -n systemctl restart pulso-rover-gateway.service
  exit 1
fi
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8765/health | grep -q '"mode":"DISARMED"'; then
    echo "gateway-ground: DISARMED and waiting for an explicit S25 lease"
    exit 0
  fi
  sleep 0.25
done
echo "Ground gateway did not become healthy; reverting to SHADOW" >&2
sudo -n rm -f "${dropin}"
sudo -n systemctl daemon-reload
sudo -n systemctl restart pulso-rover-gateway.service
exit 1
REMOTE
