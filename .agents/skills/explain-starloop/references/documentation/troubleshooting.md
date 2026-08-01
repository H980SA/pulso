# Troubleshooting

Start with deterministic inspection:

```bash
starloop doctor
starloop atlas status
starloop crew status
starloop crew events
```

## Crew is active but nothing moves

Run `starloop crew recover`. The runtime reconciles daemon PID, tmux sessions, provider sessions,
task leases, and unprocessed events. `crew.stalled` means unfinished executable work had no running
owner. `blocked_user` means only user input can continue.

## Atlas receives no automatic follow-up

Inspect whether Atlas is reported as observable. Plain provider sessions may preserve events but
cannot always be safely steered externally. Attach or start Atlas through Starloop's tmux/runtime
surface, then recover.

## A teammate stopped

Check its last disposition and task lease. Recovery resumes the saved provider session when
supported. Dirty worktree state is inspected before retrying to prevent duplicate side effects.

## A hook or tool asks for permission

Trust the installed `starloop-crew` plugin only after verifying its local Starloop source. Hook
trust is a provider safety control and may require one explicit approval after installation.
Starloop does not bypass it globally. Atlas and Forge otherwise inherit the user's provider
permission policy; Scout and Observa remain read-only.

## `/model` changed but the role did not

That is expected. Model and effort are session settings; Atlas, Forge, and Scout are instruction and
authority roles. Persist a future default explicitly rather than expecting a live `/model` change
to rewrite project configuration.

## Another directory shows different state

Run `git rev-parse --show-toplevel`. Different Git roots are isolated. Subdirectories of the same
root share state. Starloop-created worktrees are linked explicitly to their source project.
