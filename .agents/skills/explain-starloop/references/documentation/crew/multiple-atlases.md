# Multiple Atlas sessions

Atlas is a role; a project may have several Atlas instances.

- `/new` in one terminal creates a new saved conversation and makes it active there.
- Separate Codex or Claude processes can run several Atlas sessions concurrently.
- A subdirectory of the same Git root shares the Atlas registry.
- A different Git root has isolated Atlas, Crew, task, metric, and handoff-bundle state.

Each Atlas receives a stable ID and optional name, for example `atlas-main` or `atlas-billing`.
Atlases share durable project decisions but not provider context windows or `/model` settings.

Parallel Atlases require explicit ownership:

```text
auth-refresh → atlas-main
billing      → atlas-billing
```

One Atlas owns a cut. Every concurrent Crew cut uses a separate worktree and non-overlapping scope.
Another Atlas may review the same cut without becoming its owner. In v1, release the source Crew
before transferring write ownership; Starloop does not silently reassign it.

Starloop refuses two active owners for the same cut. Normal `/new` Atlas processes can still share
the main worktree, so their role overlay requires explicit non-overlapping ownership; a provider
cannot mechanically sandbox a pre-existing plain session after launch. Mutating parallel work
should use isolated Crew cuts. Cross-cut conflicts wake the owners instead of spending turns
polling for consensus.
