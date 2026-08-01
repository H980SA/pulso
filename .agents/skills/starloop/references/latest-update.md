# Latest Starloop update

Version: `1.2.0`
Updated: `2026-07-25`

Read this note once per session and change how you operate immediately. It summarizes the delta;
`SKILL.md` and its references remain canonical.

## Behavior changes

- Crew is optional; Atlas decides contextually whether it materially helps an accepted cut, briefly
  announces the choice, and honors the user's preference without applying a fixed checklist.
- The current user-facing session remains Atlas across provider, `/model`, effort, native
  compaction, goals, and cuts.
- Forge, Scout, and read-only Observa are independent tmux teammates for one bounded cut, not
  prompt-only subagents.
- Durable tasks, leases, hooks, and events drive work. A non-model daemon wakes Atlas on useful
  events; never poll with model-driven `sleep`.
- Authority is `user > Atlas > Forge > Scout`. Forge has the normal technical tools inside the
  accepted cut; Scout and Observa are mechanically restricted.
- Inspect relevant current implementation before claiming what an existing feature does. Keep it
  proportional; with Crew, use Scout when a read-only trace merits delegation.
- Concurrent Atlas cuts use isolated Git worktrees. Release refuses unfinished, dirty, or
  unintegrated work.
- Handoff is independent of Crew. It selects one project Codex or Claude session and never reads
  authentication or hidden reasoning.
- `explain-starloop` routes questions to concise installed documentation.
- The ChatGPT-web image route remains mandatory for raster generation; use built-in ImageGen only
  after its skill permits and discloses a definitive-failure fallback.
- Visual docs need an approved purpose and script; define jargon first and reject decoration.

## Update safety

- `starloop update` may replace managed skills, their lock, bundled plugins, and only the marked
  instruction block.
- It must not overwrite `.starloop/project/**`, project source, dependencies, or neighboring skills.
