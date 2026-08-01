# Crew runtime

The runtime is provider-neutral Node code. Tmux is the visible terminal surface, not the source of
truth. The runtime owns:

- Atlas and teammate registry;
- cut and task state;
- explicit peer messages;
- append-only events and metrics;
- bounded provider usage extraction without model-driven transcript summarization;
- task leases and process liveness;
- tmux pane/session metadata;
- provider session IDs and recovery;
- per-cut worktree ownership and safe cleanup.

Member states are `starting`, `running`, `waiting_event`, `blocked_user`, `idle`, `lost`, and
`stopped`. Task states are `queued`, `running`, `waiting_review`, `blocked`, `completed`, and
`failed`.

The daemon is event-driven. It consumes completion, checkpoint, review, failure, permission, and
user-direct events. Timers and OS process checks are deterministic and consume no model tokens.

If every member is idle while executable work remains, the runtime emits `crew.stalled` and wakes
Atlas. If a worker disappears or its lease expires, its task is blocked and the runtime emits
`worker.failed`. `starloop crew recover` rebuilds tmux and resumes recorded provider session IDs
when available; otherwise it starts a replacement from durable task state. It never creates an
unbounded model retry loop.

For reliable unattended wakeups, Atlas must run in a runtime-observable terminal or provider
transport. Starloop reports degraded mode when it can persist events but cannot inject a follow-up
turn into the current Atlas session.
