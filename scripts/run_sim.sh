#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "${project_root}/infra/ubuntu/pulso-env.sh"
cd "${project_root}/sim/ros2_ws"

# Ubuntu's remote-desktop session exports this as "none", which disables both
# GLX and EGL in Qt and leaves Gazebo/RViz as an otherwise healthy black window.
unset QT_XCB_GL_INTEGRATION
export QT_QPA_PLATFORM=xcb
export QT_OPENGL=desktop

existing_gazebo="$(
  pgrep -f '[i]gn gazebo (server|.*pulso_disaster\.sdf)' || true
)"
if [[ -n "${existing_gazebo}" ]]; then
  echo "Pulso Gazebo is already running (PID(s): ${existing_gazebo//$'\n'/, })." >&2
  echo "Stop that launch cleanly before starting another; two /clock publishers corrupt TF." >&2
  exit 3
fi

if [[ ! -f install/setup.bash ]]; then
  colcon build --symlink-install
  # shellcheck disable=SC1091
  set +u
  source install/setup.bash
  set -u
fi

exec ros2 launch pulso_bringup pulso_sim.launch.py "$@"
