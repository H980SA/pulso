<!-- starloop:managed:start -->
## Starloop

- For every substantive product or engineering task, invoke `$starloop` automatically before acting; the user never needs to request the skill, tools, subagents, worktrees, or checks.
- At the first substantive Starloop task in each session, read `.agents/skills/starloop/references/latest-update.md` once and adopt its behavioral changes; the canonical skill wins if the summary differs.
- Follow the research-first workflow and human gates in `.agents/skills/starloop/SKILL.md`.
- Treat `.starloop/project/` and `.starloop/starloop.json` as user-owned; do not edit `.starloop/lock.json` or the installed skill manually.
<!-- starloop:managed:end -->
