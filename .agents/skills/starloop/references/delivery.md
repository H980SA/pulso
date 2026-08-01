# Delivery Baseline

Use this protocol to turn an approved product or architecture decision into a small, reversible, evidenced delivery. The agent chooses the execution mechanics; the user should not need to request tools, subagents, or worktrees.

## Default autonomy

- Inspect the repository, instructions, dirty state, architecture, tests, and delivery tooling before editing.
- Select tools, subagents, and isolated worktrees independently when they improve speed or confidence.
- Keep local, reversible implementation work autonomous. Ask before destructive cleanup, external publication, merge, deployment, user-visible communication, expense, or a product decision that changes scope.
- Define acceptance criteria and the cheapest convincing evidence before implementation.
- Preserve user changes and stop at the requested boundary.

## Choose the execution shape

| Shape      | Use when                                                                                        | Rule                                                                     |
| ---------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Local      | One coherent edit or tightly coupled files                                                      | One agent owns implementation and verification                           |
| Sequential | Tasks share contracts, schema, files, or integration order                                      | Resolve the contract first; implement and verify one slice at a time     |
| Parallel   | Tasks are independent, bounded, and have disjoint write scopes, or are read-only investigations | Assign explicit inputs, outputs, file ownership, and completion evidence |

Do not parallelize overlapping edits, an unresolved data model or public contract, destructive operations, or work whose integration order is unclear. Parallelism is a latency optimization, not a substitute for ownership.

## Parallel work protocol

1. The coordinator defines the outcome, constraints, interfaces, risk tier, write scope, and expected evidence.
2. Give each concurrent writer one isolated worktree and one non-overlapping scope. One writer owns each file or interface at a time.
3. Let read-only research run concurrently when it cannot mutate shared state.
4. Require each worker to return a concise result: outcome, changed files, decisions, checks, risks, and unresolved items.
5. The coordinator reviews and integrates outputs sequentially, one slice at a time.
6. After every integration, re-run the affected contract and checks before integrating the next slice.
7. Resolve conflicts deliberately against the agreed contract; never accept an automatic conflict resolution without review.

Worktrees are an internal execution detail. Do not make the user create, switch, clean, or manage them, and do not include worktree commands in the user-facing handoff.

## Worktree safety

Before switching, rebasing, deleting a branch, or removing a worktree, inspect its status, untracked files, commits, and stashes.

- Refuse destructive cleanup while a worktree is dirty or ownership is uncertain.
- Preserve changes through an owner-approved commit, patch, or stash, or leave the worktree intact and report the blocker.
- Never use hard reset, forced clean, forced deletion, or overwrite merely to make checks pass.
- Never discard generated-looking files until their origin and disposability are confirmed.
- Remove an isolated worktree only after its result is integrated or explicitly abandoned and its state is clean.

## Git governance

Choose governance by operating stage; do not install remote ceremony before it pays for itself.

- **Solo/internal:** keep coherent local commits on `main`. Use branches or worktrees only for
  parallel, risky, or experimental work. Run the repository's deterministic local gate before
  integrating. Do not require hosted CI, pull requests, or branch protection merely because Git is
  present.
- **Shared/remote:** use trunk-based development, short-lived branches, pull requests, and a stable
  required check once multiple contributors or remote review need integration protection.
- **Public/production:** add protected `main`, release evidence, supply-chain controls, and
  accountable review proportional to risk.

- Keep `main` as the only long-lived branch. Environments are deployments, not branches.
- When the shared/remote gate is active, protect `main`: require a pull request, stable required
  check, resolved conversations, and linear history; block force-push, direct push, and deletion.
- Use short-lived branches with this grammar: `<type>/<optional-id>-<kebab-summary>`.
- Allow these types: `feat`, `fix`, `security`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`, `spike`, `hotfix`.
- Keep one outcome per branch. Target hours and at most two working days; split longer work behind compatible contracts or flags.
- Do not add personal, tool, or `codex/` prefixes. Authorship belongs in commits and review metadata.
- Treat `spike/*` as disposable research. Extract production work into a normal branch rather than merging the spike directly.
- Reserve `hotfix/*` for urgent production correction. Prefer rollback or feature disablement first, then use normal gates.
- Delete merged branches automatically.

Use [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):

`<type>(<scope>)!: <imperative summary>`

- Explain why and notable tradeoffs in the body.
- Use `BREAKING CHANGE:` and issue references in footers when applicable.
- Keep commits coherent and buildable. Do not mix unrelated cleanup into a feature.

When pull requests are active, prefer squash merge. Make the PR title a valid Conventional Commit;
it becomes the single `main` commit. State outcome, decisions, risk tier, evidence,
schema/migration impact, security impact, rollout, rollback, and documentation changes.

Use review proportional to risk:

- Low: author self-review plus deterministic gates.
- Medium: independent agent review plus targeted evidence.
- High: independent security/domain review, threat-model and migration evidence where applicable, and explicit human merge authorization.

Do not configure an impossible human-approval rule for a solo founder. Add CODEOWNERS and required second-human approval when another accountable human exists. Agents may prepare auto-merge, but merge only after the user's authorization. Introduce a merge queue only when concurrent ready PRs make stale-base failures frequent.

## CI lanes and budgets

Do not create hosted CI by default. Activate it when at least one trigger exists: multiple
contributors, remote pull requests, automated releases or deployments, external consumers,
cross-platform support claims, or required audit evidence. Until then, keep one reproducible local
verification command and exercise the exact release artifact manually.

When CI is justified, optimize for fast feedback without weakening high-risk gates.

| Lane         | Target                               | Required work                                                                                                            |
| ------------ | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| Pre-commit   | Under 10 seconds                     | Format or lint only changed files; secret scan of staged content                                                         |
| Pre-push     | Under 90 seconds                     | Affected type checks, unit tests, and contract checks                                                                    |
| Pull request | p95 under 5 minutes                  | Deterministic gate, affected build/tests, targeted integration and security checks, migration validation when applicable |
| Main/release | Complete, not artificially shortened | Full build, integration/e2e, release scans, SBOM/provenance, immutable artifact, deployment readiness                    |
| Nightly      | Slow checks allowed                  | Full matrix, deeper SAST/SCA/DAST, fuzz/load tests, restore drill, flaky-test detection                                  |

- Start the PR workflow for every PR. Detect affected scope inside jobs; do not skip the entire required workflow with path filters.
- Always finish through one stable aggregate status named `ci / gate`, including a successful no-op result when nothing applies.
- Parallelize independent jobs, cache by lockfile/toolchain, cancel superseded runs, and reuse outputs within the run.
- If impact analysis is uncertain, run the full relevant suite.
- Run enhanced PR gates immediately for authentication, authorization, tenancy, payments, migrations, public APIs, infrastructure, and AI tools; do not defer them to nightly.
- Treat flaky tests as defects. Quarantine with an owner and expiry only when necessary; never hide them with blind retries.
- Measure the p95 PR duration monthly and remove duplicated setup, serial bottlenecks, and low-value checks.

## Build, release, and rollback

- Build a release artifact once after trusted checks. Address it by immutable digest and promote that same artifact through environments.
- Attach source revision, dependency lock, test result, SBOM, provenance, scans, configuration version, and approval to the release record.
- Separate deployment from release with backward-compatible contracts and feature flags when risk warrants it.
- Use expand-migrate-contract for schema changes. Verify old and new application versions against the transition state.
- Define rollback criteria before deployment. Prefer disabling a flag or redeploying the prior artifact; use a tested forward fix when data migration is irreversible.
- Verify health, critical user journeys, telemetry, and data integrity after deployment. Stop or roll back on breached thresholds.
- Sign release tags and attest artifacts when the delivery platform supports managed signing; record any missing capability instead of claiming it exists.

## Required evidence

Collect evidence proportional to the risk and affected surface.

- **Functional:** acceptance tests, contract tests, relevant integration/e2e results, and a runtime smoke test.
- **Observability:** structured logs, correlation identifiers, relevant metrics/traces, failure visibility, and an alert or dashboard check for new critical paths.
- **Performance:** an explicit budget, representative before/after measurement, query and payload review, and load or Core Web Vitals evidence when applicable.
- **Accessibility:** for user interfaces, automated checks plus keyboard, focus, semantics, contrast, zoom/reflow, and screen-reader spot checks against applicable [WCAG 2.2](https://www.w3.org/TR/WCAG22/) Level AA criteria.
- **Security:** the risk-control-test-evidence-residual-risk chain from `security.md`.
- **Operations:** rollout steps, rollback trigger and procedure, migration/restore evidence, and ownership of follow-up risks.

For UI work, inspect the rendered result, interaction states, console, network behavior, responsive layouts, and accessibility tree. Use screenshots or other multimodal evidence only when visual behavior matters. For backend work, exercise the real boundary and inspect response, persistence, logs, metrics, and traces where available.

## Token-efficient verification

Use an evidence ladder. Start cheap and deterministic, then deepen only as risk or failure demands:

1. Inspect the focused diff, repository status, generated changes, and formatting.
2. Run affected lint, types, unit, contract, and migration checks.
3. Run targeted integration/build checks at the changed boundary.
4. Exercise the real runtime path and inspect persistence and telemetry.
5. Add visual, accessibility, performance, security, or failure-injection evidence when the surface requires it.
6. Request independent review for Medium and High risk or when uncertainty remains.

Reduce waste without reducing confidence:

- Search before reading whole files; inspect changed symbols and their consumers first.
- Batch independent read-only tool calls and delegate bounded research.
- Prefer affected tests and machine-readable summaries; run the full suite when impact is uncertain or at release gates.
- Return failing excerpts and final summaries, not unbounded logs or duplicate transcripts.
- Re-run only checks invalidated by the latest change, plus the stable aggregate gate.
- Stop when acceptance criteria, risk gates, runtime evidence, and rollback readiness are satisfied; do not keep polishing outside scope.

## Delivery report

End every delivery with a compact, evidence-backed report:

- outcome and user-visible behavior;
- files and contracts changed;
- decisions and tradeoffs;
- checks run and results;
- checks not run and why;
- security, privacy, data, accessibility, performance, and operational impact;
- rollout, rollback, residual risks, and follow-ups.

Do not claim success from code inspection alone when the behavior can be run. Do not claim a check, standard, signature, deployment, or certification that was not actually evidenced.
