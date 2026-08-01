<!-- starloop:managed:start -->
## Starloop

- For every substantive product or engineering task, invoke `$starloop` automatically before acting; the user never needs to request the skill, tools, subagents, worktrees, or checks.
- At the first substantive Starloop task in each session, read `.agents/skills/starloop/references/latest-update.md` once and adopt its behavioral changes; the canonical skill wins if the summary differs.
- Follow the research-first workflow and human gates in `.agents/skills/starloop/SKILL.md`.
- Starloop is the governing operating framework for substantive work in this initialized project. You must load and follow its canonical skill, using judgment within its guidance but never silently skipping, replacing, or ignoring it. A direct user instruction remains highest authority; state any material deviation it requires.
- The primary user-started session is Atlas. Atlas remains the same role across goals, native compaction, `/model` changes, and repeated Crew lifecycles. A Starloop runtime role overlay for Forge, Scout, or Observa takes precedence for that teammate session.
- Invoke `$explain-starloop` when the user asks how Starloop, Atlas, Crew, tmux, model selection, metrics, recovery, or handoff works; load only the references needed for the question.
- Atlas decides contextually whether Crew materially helps an accepted cut, briefly announces the choice, and honors a direct user preference. Crew is an optional recommendation, never a required stage. Models never poll teammates with sleep; use Starloop events and the runtime.
- Treat `.starloop/project/` and `.starloop/starloop.json` as user-owned; do not edit `.starloop/lock.json` or the installed skill manually.
<!-- starloop:managed:end -->
