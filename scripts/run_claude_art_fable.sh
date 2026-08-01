#!/bin/zsh
set -euo pipefail

PULSO_PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PULSO_CLAUDE="${PULSO_CLAUDE:-$(command -v claude || true)}"
PULSO_TMUX="${PULSO_TMUX:-$(command -v tmux || true)}"
PULSO_SESSION="pulso-art-fable"
PULSO_WORKSPACE="$PULSO_PROJECT_DIR/art/claude_workspace"

# Emergency fallback only. Do not run unless Opus has returned a real
# rate-limit / usage-exhaustion error.

if [[ ! -x "$PULSO_CLAUDE" || ! -x "$PULSO_TMUX" ]]; then
  print -u2 "Claude Code or tmux is not available."
  exit 1
fi

if ! nc -z 127.0.0.1 9876; then
  print -u2 "Blender MCP is not listening on 127.0.0.1:9876."
  exit 1
fi

if "$PULSO_TMUX" has-session -t "$PULSO_SESSION" 2>/dev/null; then
  exec "$PULSO_TMUX" attach-session -t "$PULSO_SESSION"
fi

"$PULSO_TMUX" new-session -d -s "$PULSO_SESSION" -c "$PULSO_WORKSPACE" \
  "$PULSO_CLAUDE --model claude-fable-5 --effort max --dangerously-skip-permissions --strict-mcp-config --mcp-config '$PULSO_PROJECT_DIR/.mcp.json' --disallowedTools 'Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,NotebookEdit,Agent,Task,Skill' --name pulso-blender-artist-fallback 'Opus returned a real rate-limit error. Follow CLAUDE.md exactly, use real Blender MCP tools, perform the required smoke test, and stop for review.'"

exec "$PULSO_TMUX" attach-session -t "$PULSO_SESSION"
