# Feature Design

Turn an approved product outcome into the smallest implementation-ready decision without document sprawl.

## Lead the design interview

- Ask only questions whose answers change behavior, data, architecture, security, testing, cost, or rollout.
- Present a recommended default, viable alternatives, and concrete tradeoffs.
- Use hypothetical failures and scale changes to expose hidden assumptions.
- Teach through the discussion; never require the user to perform the analysis alone.

## Define the feature

1. State the user or system outcome, success signal, actors, scope, and non-goals.
2. Name the owning business domain and code module. List collaborating modules and forbidden dependencies.
3. Model the task flow and every meaningful state. Load [experience-design.md](experience-design.md) for user-facing work.
4. Define entities, relationships, ownership, lifecycle, state transitions, and invariants.
5. Define source of truth, queries, indexes, transactions, migrations, retention, deletion, and tenant boundary.
6. Define APIs, events, jobs, files, errors, versioning, and authorization.
7. Define concurrency, idempotency, ordering, retries, timeouts, partial failure, cache behavior, and provider failure.
8. Load [security.md](security.md) and define threats, privacy boundaries, abuse cases, audit needs, and security evidence.
9. Define acceptance, unit, integration, contract, security, end-to-end, failure, performance, and UX evidence proportionally to risk.
10. Define observability, rollout, migration, compatibility, rollback, and removal conditions.

## Continue an implemented feature from evidence

When a request names an existing feature or asserts current behavior, treat the claim as unverified
until inspected in the current checkout. Locate the relevant executable path, then follow only the
callers, state, persistence, configuration, consumers, tests, or runtime behavior needed to answer
the question safely. Documentation and memory are useful leads, not proof. Tests describe intended
or protected behavior; claim runtime behavior only when proportionate runtime evidence supports it.

Keep the investigation proportional. Stop when the requested claim is supported or the remaining
uncertainty is clear. Explain the result naturally instead of forcing every feature into a taxonomy.

With active Crew, Atlas should use read-only Scout when the trace is substantial enough to benefit
from delegation; a quick local check can remain with Atlas. Scout returns locations, flow,
evidence, contradictions, and uncertainty. Atlas validates material evidence and owns conclusions
or design decisions. Atlas or Forge performs proof that needs writes or mutable runtime access.

## Pressure-test the proposal

Select relevant scenarios instead of asking all of them:

- Process the same request, payment, or webhook twice.
- Receive events late, out of order, or after deletion.
- Run concurrent writes against the same invariant.
- Lose the database, cache, queue, network, worker, or external provider midway.
- Serve stale cache or a partially completed migration.
- Attempt cross-tenant or object-level access with a valid session.
- Increase traffic, data, tenants, or fan-out by 10x, 100x, and 1000x.
- Exhaust a quota, exceed a cost budget, or trigger deliberate abuse.
- Roll forward and backward while old clients and jobs remain active.
- Operate and investigate the feature at 03:00 with only logs, metrics, traces, and runbooks.

When distribution, public launch, real-time fan-out, AI inference, or another metered dependency can
create a concentrated spike, load [system-design.md](system-design.md) and include its concise Viral
Readiness block. Skip the block for work whose demand and cost cannot materially affect the design.

## Keep one lean capsule

Use one feature capsule by default:

```text
Outcome and evidence
Scope and non-goals
Actors and flows
Owning domain and modules
Data, states, and invariants
Contracts and failure behavior
Security and privacy
Acceptance evidence
Rollout and rollback
Decisions and open risks
```

Link to executable schemas, contracts, migrations, tests, or diagrams instead of duplicating them. Create a separate durable decision record only for a consequential choice that is expensive to reverse.

## Establish the gate

- Summarize the chosen design, rejected alternatives, risks, and planned evidence.
- Resolve every material ambiguity or make it an explicit user decision.
- Wait for the user's go before production implementation.
- After the go, implement acceptance-first in small vertical slices and continue autonomously until the agreed evidence passes.
