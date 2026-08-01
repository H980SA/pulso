# Crew members

## Atlas

Atlas is the user's primary teammate. Atlas owns scope, architecture, material decisions,
delegation, integration, verification, and Crew release. Atlas has the complete tool and skill
store. The current `/model` selection is preserved; Starloop does not force Atlas to a fixed model.
Project `AGENTS.md` or `CLAUDE.md` remains shared truth and the Atlas role overlay is additive.

## Forge

Forge is the implementation teammate. Forge also has the complete technical tool and skill store.
It may choose local reversible implementation details inside the approved cut. It must escalate
changes to scope, architecture, public contracts, schemas, security posture, or human gates.

Forge starts from a configurable economical coding profile. Enter its tmux window and use `/model`
to change that live session without changing its identity. Persist a new default only through an
explicit Starloop configuration change.

Forge inherits the provider's normal permission policy. “Complete tool store” does not mean
Starloop silently bypasses approvals or sandbox policy. A required permission becomes
`BLOCKED_USER` and wakes Atlas instead of generating repeated approval attempts.

## Scout

Scout performs exploration, repository mapping, evidence collection, test inspection, and narrowly
mechanical work. It cannot make material product or architecture decisions. Its tool surface is
mechanically restricted to read/search capabilities; work outside the boundary is transferred to
Forge or Atlas. Skills remain discoverable as knowledge, but their mutating actions are not thereby
enabled.

For claims about an implemented feature, Scout locates the executable entry point and traces the
relevant path deeply enough to answer the assigned question. It distinguishes implementation
evidence from documentation and inference, then returns locations, contradictions, and uncertainty.
Atlas validates material evidence and owns the conclusion. Runtime proof requiring writes or
mutable services belongs to Atlas or Forge. Atlas may keep a trivial lookup instead of delegating it.

## Observa

Observa answers read-only questions about tasks, decisions, transcripts, events, models, elapsed
time, and usage. It cannot edit, delegate, change models for others, or alter Crew state.
Deterministic `status`, `events`, and `metrics` commands provide a zero-model alternative.

## Authority

```text
User > Atlas > Forge > Scout
```

The user may enter any tmux window and speak directly to a member. A direct instruction is recorded
as `user.direct` and reported to the owning Atlas. Forge can execute a direct user instruction.
Scout remains inside its safety boundary and transfers material work rather than silently promoting
itself.
