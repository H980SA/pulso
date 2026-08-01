# Safety and ownership

Starloop separates three ownership zones:

```text
src/ and package plugins       package engine
content/                       installable knowledge
.starloop/project/             user and project truth
```

Managed skill projections and delimited instruction blocks update only when their recorded hashes
remain clean. Project configuration, product artifacts, Crew state, handoffs, accepted visuals, and
surrounding `AGENTS.md` or `CLAUDE.md` content are never silently replaced.

Atlas and Forge have the complete technical tool store. Authority remains bounded by the approved
cut and user gates. Scout and Observa receive mechanical restrictions. Skill visibility is context
management, not a security boundary; the runtime and provider permissions enforce action limits.
Starloop never enables a global permission bypass. Provider or operating-system approval that is
still required is surfaced as a durable blocker.

Parallel writes require isolated worktrees. Cleanup refuses dirty, unintegrated, unknown, symlinked,
or out-of-scope paths. Runtime state is project-scoped and ignored from Git by default; durable
product decisions remain under `.starloop/project/`.

The Crew hook is installed at user scope but checks the project lock before doing anything. An
older initialized project stays inert until that project explicitly runs `starloop update`.

Handoff is independent of Crew. Its selected transcript and summary may contain proprietary project
information, so Starloop keeps the bundle local by default and never includes provider credentials,
system/developer instructions, tool payloads, or hidden reasoning.
