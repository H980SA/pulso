#!/usr/bin/env bash
set -euo pipefail

# The physical phone reaches this evidence-only socket over the private field
# Wi-Fi. The topic allowlist below keeps it separate from motor control.
readonly bridge_port="${PULSO_ROSBRIDGE_PORT:-9091}"
readonly bridge_address="${PULSO_ROSBRIDGE_ADDRESS:-0.0.0.0}"
readonly evidence_glob="['/pulso/hil/observation','/pulso/navigation/candidates','/pulso/hil/action_result','/pulso/navigation/metaview/compressed','/pulso/navigation/metaview_scene','/pulso/phone/rgb/compressed','/pulso/phone/rgb/camera_info','/pulso/phone/telemetry','/pulso/hil/perception_tracks','/pulso/hil/brain_trace','/pulso/hil/gemma_input','/pulso/hil/gemma_view/compressed','/pulso/hil/perception_telemetry','/pulso/operator/command']"

exec ros2 run rosbridge_server rosbridge_websocket --ros-args \
  -p "port:=${bridge_port}" \
  -p "address:=${bridge_address}" \
  -p authenticate:=false \
  -p ssl:=false \
  -p max_message_size:=4000000 \
  -p "topics_pub_glob:=\"${evidence_glob}\"" \
  -p "topics_sub_glob:=\"${evidence_glob}\"" \
  -p 'services_glob:="[]"' \
  -p 'actions_glob:="[]"'
