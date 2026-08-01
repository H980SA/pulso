# Getting started

## Install the local package

Until Starloop is published, clone the repository, install its development dependencies, and link
the CLI:

```bash
git clone git@github.com:VEYON-DEV/starloop-agentic-framework.git
cd starloop-agentic-framework
npm ci
npm run link:local
```

## Initialize one project

Run exactly one initial adapter:

```bash
starloop init --codex
# or
starloop init --claude

starloop doctor
```

Start Codex or Claude from that Git repository. A normal `/new` is the primary Atlas session after
Crew knowledge is installed. Native provider compaction remains responsible for long conversation
history.

## Daily use

- Describe the outcome normally; Starloop loads implicitly for substantive work.
- Discuss material choices and establish the human gate.
- Say `GO` when the bounded cut is ready for implementation.
- Keep Atlas alone for ordinary work.
- Say “Atlas, start Crew for this cut and release it when complete” when parallel economical work
  has a positive payoff.
- Change `/model` at any time. Identity and authority do not change with the model.

## Update

Update the linked Starloop checkout, then update the target project:

```bash
git pull --ff-only
npm ci
npm run link:local

cd /path/to/project
starloop update --check
starloop update --dry-run
starloop update
starloop doctor
```

`init` and `update` replace only clean managed projections. They never overwrite
`.starloop/project/**`, Crew state, handoffs, or user configuration.

Crew and the independent handoff capability are gated by the installed project lock. Rebuilding or
relinking the global CLI does not activate them in an existing project. Each project adopts this
large behavior change only after its own explicit `starloop update`; a fresh `init` installs it
immediately.
