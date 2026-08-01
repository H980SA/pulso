# System Design

Choose the simplest architecture that satisfies measured product, security, reliability, performance, and operational constraints.

## Establish the model

- Treat a domain as a business capability and language boundary.
- Treat a module as an enforceable code and dependency boundary.
- Treat a feature as a vertical outcome that may cross several modules while retaining one clear owner.
- Prefer a well-structured deployable unit, often a modular monolith for a new SaaS, until evidence justifies distribution.
- Isolate providers behind adapters and keep core rules provider-neutral.

## Design from constraints

- Define actors, trust boundaries, tenancy, regions, sensitive data, compliance scope, and external systems.
- Define traffic, data volume, growth, fan-out, latency, availability, durability, recovery, and cost envelopes with ranges.
- Identify the source of truth and the consistency required for each invariant.
- Draw only the smallest useful context, container, sequence, or data-flow view.

## Design data deliberately

- Model entities, cardinalities, ownership, state machines, and invariants before tables.
- Enforce invariants with database constraints and transactions where possible.
- Design from real read and write paths; add indexes with a query and expected selectivity.
- Define tenant scoping, authorization, retention, deletion, audit, migration, backfill, and rollback.
- Keep cache derivative and disposable. Namespace every key by environment and isolation boundary; define TTL, invalidation, stampede control, and stale behavior.

## Choose runtime boundaries

- Keep synchronous work inside the request only when the caller needs the result immediately and the dependency can meet the latency and reliability budget.
- Use asynchronous work for buffering, fan-out, long processing, retryable integration, or independent lifecycle.
- Define idempotency keys, ordering, retry limits, backoff, poison handling, replay, and observability before adding a queue.
- Use an outbox or equivalent atomic handoff when a database change and external event must not diverge.
- Add replicas, partitions, workers, services, regions, or orchestration only for a named bottleneck or ownership need.

## Run the senior pressure test

- Identify the first bottleneck at current, 10x, 100x, and 1000x load.
- Compare vertical scaling, horizontal scaling, batching, caching, and simpler product limits before splitting services.
- Test concurrent writes, hot keys, noisy tenants, retry storms, thundering herds, clock differences, partial deploys, and regional failure.
- Explain consistency versus availability choices per operation, not with a system-wide slogan.
- Calculate rough throughput, storage growth, bandwidth, queue depth, provider quotas, and dominant cost where they influence design.
- Define graceful degradation, recovery, rollback, and how an operator detects and diagnoses failure.

## Design for burst and overload

Apply this section when acquisition can concentrate demand, a public launch may go viral, the
product uses metered external compute, or traffic is otherwise bursty.

- Express demand as a load unit over time, not registered users: concurrent sessions, requests,
  messages, jobs, fan-out, tokens, bytes, or another workload-specific unit.
- Model current, expected launch, viral peak, and hard safety ceiling. Separate architecture that
  can scale from capacity provisioned and paid for today.
- Identify ceilings that compute autoscaling cannot remove: database connections and write
  throughput, provider quotas, regional limits, cold starts, queue consumers, payment or email
  limits, and spend rate.
- Admit work before expensive allocation. Apply per-actor and global rate, concurrency, payload,
  and cost limits; keep queues bounded with deadlines; reject excess work early and retryably.
- Define a product-approved degradation order. Preserve critical state and core journeys while
  delaying or disabling expensive, asynchronous, low-priority, or optional work.
- Add budget alerts, metered-usage caps, and tested kill switches or economic circuit breakers for
  dependencies whose cost can grow with traffic.
- Keep retries bounded, idempotent, and jittered so overload does not amplify itself. Recover
  gradually instead of releasing the entire backlog at once.
- Load test the intended peak, overload behavior, degradation path, recovery, and cost envelope.
  Prove the system stays consistent even when it cannot serve every request.

Capture one concise Viral Readiness block in the feature capsule or product foundation:

```text
Load unit and time window
Current / launch / viral / hard-ceiling demand
Data, provider, regional, and cost ceilings
Provisioned capacity, elasticity, cold starts, and scale-up time
Admission, concurrency, queue, timeout, and retry limits
Degradation priority and user-visible behavior
Spend alerts, circuit breakers, and kill switches
Peak / overload / recovery test and operational evidence
Trigger for the next architectural step
```

Do not promise unlimited scale. Design a simple system that scales to a named envelope and remains
safe beyond it. Revalidate overload and elasticity mechanisms against current provider guidance;
use [Google Cloud graceful degradation](https://docs.cloud.google.com/architecture/framework/reliability/graceful-degradation),
[Google SRE overload guidance](https://sre.google/sre-book/addressing-cascading-failures/), and the
selected platform's official architecture framework as starting points.

## Require operational proof

- Define service-level indicators and objectives only for user-important behavior.
- Emit privacy-safe structured logs, metrics, traces, correlation identifiers, and audit events.
- Verify backup restoration, migrations, capacity assumptions, timeout paths, and dependency failure proportionally to risk.
- Load [security.md](security.md) for threat boundaries and [delivery.md](delivery.md) for release and runtime evidence.
- Record the trigger that would justify the next architectural step; do not buy complexity in advance.
