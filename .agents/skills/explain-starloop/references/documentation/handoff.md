# Handoff

Handoff summarizes one local Codex or Claude conversation so work can continue in another terminal,
account, or provider. It is scoped to the current Git root and is completely independent of Crew:
no Atlas registry, cut, task, teammate, event, metric, or tmux state is required or mutated.

## What it captures

- source provider, session ID, local transcript path, and source working directory;
- a concise agent-authored summary when supplied;
- otherwise, a mechanical digest of the latest explicit user and assistant messages;
- a bounded Markdown transcript containing explicit user and assistant text only;
- Git status, recent commits, and a bounded tracked working-tree patch.

It excludes unrelated Git projects, provider authentication, cookies, system/developer
instructions, tool payloads, and hidden reasoning. The transcript format belongs to each provider,
so Starloop reads it defensively and skips unknown records.

## Typical flow

```bash
starloop handoff list
starloop handoff create --codex --session latest
starloop handoff create --claude --session <id-or-absolute-jsonl-path>
starloop handoff status

# Change account/provider, open the same Git project, then:
starloop handoff resume --latest
```

The project's configured adapter is the default source, but `--codex` or `--claude` can select the
other provider. Use an absolute JSONL path when a session lives under another local Codex profile.
When several conversations exist for the same repository, prefer an explicit session ID or path
instead of `latest`.

The source agent may pass `--summary <text>` or `--summary-file <project-relative-path>`. That
semantic summary should state accepted decisions, current implementation state, verification,
risks, and the next action. Without it, the receiving agent must treat the mechanical digest as an
orientation aid and verify it against `transcript.md` and the current worktree.

Bundles live under `.starloop/handoffs/` and are ignored locally. Explicit prompts, summaries, and
Git diffs can still contain secrets; inspect a bundle before sharing it. Handoff provides functional
continuity, not a clone of a provider context window or private state.
