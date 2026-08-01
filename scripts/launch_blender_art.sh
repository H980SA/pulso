#!/bin/zsh
set -euo pipefail

PULSO_PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PULSO_BLENDER="/Applications/Blender.app/Contents/MacOS/Blender"
PULSO_ADDON="$PULSO_PROJECT_DIR/.tools/vendor/blender-mcp/addon.py"

if [[ ! -x "$PULSO_BLENDER" ]]; then
  print -u2 "Blender 5.2 executable not found at $PULSO_BLENDER"
  exit 1
fi

if [[ ! -f "$PULSO_ADDON" ]]; then
  print -u2 "Pinned Blender MCP addon not found at $PULSO_ADDON"
  exit 1
fi

export PULSO_PROJECT_DIR
export DISABLE_TELEMETRY=true
export BLENDER_HOST=127.0.0.1
export BLENDER_PORT=9876

exec "$PULSO_BLENDER" \
  --python "$PULSO_PROJECT_DIR/scripts/blender_mcp_bootstrap.py"

