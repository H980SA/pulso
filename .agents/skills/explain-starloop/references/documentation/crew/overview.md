# Crew overview

Crew is an optional capacity used by the primary Atlas session. It is not a Codex Goal and the
teammates are not disposable prompt-only subagents.

```text
Atlas working alone
        │
        ├── many conversations, goals, and vertical cuts
        │
        └── start Crew for one cut
              ├── Forge
              ├── Scout
              └── Observa
                    │
                    └── release teammates; Atlas continues
```

Atlas is the role of the user-facing session created with `/new`. It survives native compaction,
model and effort changes, many goals, and repeated Crew lifecycles. Releasing Crew closes the
temporary teammates and runtime resources, never the Atlas conversation.

Crew members are independent provider sessions with their own context windows, transcripts, model
selection, inbox, tasks, and terminal surface. They communicate through a project-scoped event log
and explicit messages. They may inspect explicit transcripts and decision rationales, but no member
can read another model's hidden chain of thought.

The project may contain multiple Atlas sessions. Each is an instance of the same role with a unique
identity and ownership scope.
