---
name: explain-starloop
description: Explain Starloop accurately and concisely from its installed documentation. Use when a user asks what Starloop is, how it helps, how to initialize or update it, how Atlas or Crew works, how models and tmux interact, how recovery or handoff works, how multiple Atlas sessions stay isolated, how usage is measured, or how to get more value from Starloop.
---

# Explain Starloop

Answer from the smallest relevant set of references. Do not load the whole documentation tree.

- Read [overview.md](references/documentation/overview.md) for the product purpose and boundaries.
- Read [getting-started.md](references/documentation/getting-started.md) for installation, project
  isolation, daily use, and updates.
- Read [crew/overview.md](references/documentation/crew/overview.md) for the Crew mental model.
- Read [crew/members.md](references/documentation/crew/members.md) for Atlas, Forge, Scout, Observa,
  authority, tools, models, and direct tmux interaction.
- Read [crew/lifecycle.md](references/documentation/crew/lifecycle.md) for start, event-driven work,
  completion, release, recovery, and native compact behavior.
- Read [crew/multiple-atlases.md](references/documentation/crew/multiple-atlases.md) for multiple
  `/new` sessions, ownership, parallel cuts, and worktrees.
- Read [crew/runtime.md](references/documentation/crew/runtime.md) for daemon, events, task states,
  liveness, tmux, and failure recovery.
- Read [crew/models-and-metrics.md](references/documentation/crew/models-and-metrics.md) for model
  defaults, `/model`, token savings, allowance observations, and benchmarks.
- Read [handoff.md](references/documentation/handoff.md) for account/provider continuity and its
  limits.
- Read [evidence.md](references/documentation/evidence.md) when the user asks what an implemented
  feature currently does, wants to continue or modify it, or reports a mismatch between prose and
  runtime.
- Read [commands.md](references/documentation/commands.md) for exact CLI commands and natural
  language equivalents.
- Read [safety-and-ownership.md](references/documentation/safety-and-ownership.md) for managed
  files, project-owned state, permissions, isolation, and cleanup.
- Read [troubleshooting.md](references/documentation/troubleshooting.md) only for diagnosis.

State whether behavior is automatic, requires an explicit user instruction, or is a fallback.
Never describe a goal, model, provider thread, teammate, cut, or Crew as interchangeable. If the
installed CLI behavior conflicts with prose, inspect `starloop --help` and `starloop doctor`; report
the observed behavior and flag the documentation drift.
