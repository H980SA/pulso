# Commands

## Installation

```bash
starloop init --codex
starloop init --claude
starloop update --check
starloop update --dry-run
starloop update
starloop doctor
```

## Atlas

```bash
starloop atlas start --codex
starloop atlas start --claude
starloop atlas list
starloop atlas status
starloop atlas name <name>
starloop atlas retire <atlas-id>
```

## Crew

```bash
starloop crew start --cut <slug>
starloop crew status
starloop crew attach [forge|scout|observa|runtime]
starloop crew recover
starloop crew release
starloop crew events
starloop crew metrics
starloop crew benchmark
```

Atlas uses task and message subcommands internally; users normally speak to Atlas instead:

```bash
starloop crew task create --assignee <forge|scout> --title <title> \
  --prompt <bounded-task>
starloop crew task complete --id <task-id> --summary <acceptance-evidence>
starloop crew task block --id <task-id> --blocker <reason>
starloop crew send <forge|scout|observa> --prompt <message>
starloop crew model <forge|scout> --model <future-default> --effort <level>
```

`crew model` changes persisted configuration for recovery or future launches. Use `/model` inside
the teammate's tmux pane to change that live provider session.

## Handoff

```bash
starloop handoff list [--codex|--claude]
starloop handoff create [--codex|--claude] [--session <id|latest|absolute-jsonl-path>]
  [--summary <text>|--summary-file <project-relative-path>]
starloop handoff # shorthand for create with the configured provider and latest project session
starloop handoff status
starloop handoff resume --latest
```

Natural language is equivalent when the agent has Starloop installed:

- “Start Crew for this cut and release it when complete.”
- “What is Forge doing?”
- “Recover the active Crew.”
- “Summarize this Codex session so I can continue it from Claude.”
- “Resume the latest handoff.”
- “Keep Forge on this new model by default.”

Read-only status commands never start a model or mutate external systems.
