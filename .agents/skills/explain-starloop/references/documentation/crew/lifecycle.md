# Crew lifecycle

## Start

The user may request or decline Crew directly. Atlas may also recommend and start it after a cut is
accepted when independent work or sustained parallel progress materially outweighs coordination
cost. This is contextual judgment, not a required Starloop phase or fixed checklist, and Atlas
briefly announces the choice.

`starloop crew start` records a bounded cut, acceptance evidence, ownership, and whether it should
receive an automatic release-ready event. The Git base must be clean because the runtime creates an
isolated branch and worktree. It then starts Forge, Scout, Observa, task state, metrics, and tmux
surfaces.

## Work

A completed model turn is not a completed task. Each member finishes a turn with one disposition:

```text
DONE
WAITING_FOR
BLOCKED_USER
BLOCKED_TEAMMATE
FAILED
CHECKPOINT
```

Atlas may end its turn while Forge or Scout works. A non-model daemon waits for events and wakes the
appropriate existing session only when progress, review, failure, or user input requires it. Models
never poll with `sleep`.

## Complete and release

Before release Atlas verifies acceptance criteria, tests, task state, and decisions, commits Crew
work, integrates the Crew branch, and verifies the integrated result. `starloop crew release`
closes Forge, Scout, Observa, and the clean integrated worktree. Atlas remains in the same provider
conversation.

An instruction such as “release Crew when the cut is complete” authorizes Atlas to release after
verification. The deterministic runtime emits `crew.release_ready`; it does not perform product
acceptance. A pending human gate, dirty or unintegrated work, or incomplete task blocks release.

## Recover

`starloop crew recover` reconciles persisted state with real processes, tmux panes, sessions,
worktrees, and event offsets. A dead worker resumes from its provider session when possible and from
its durable checkpoint otherwise. If the machine sleeps, local work pauses and reconciliation runs
after the machine returns.

Native Codex or Claude compaction remains active for every member. Starloop does not automatically
replace Atlas's conversation or run an LLM context-cleaner after each turn.
