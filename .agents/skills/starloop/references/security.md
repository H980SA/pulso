# Security Baseline

Use this baseline for every production product. Apply the core controls to all work and activate the profiles that match the product. Pin the exact source versions in the project's security profile; do not silently follow `latest`.

## Operating rule

For every material risk, preserve this chain:

`risk -> control -> test -> evidence -> residual risk`

- Make security proportional to impact, not to feature size.
- Prefer secure defaults, least privilege, deny by default, and defense in depth.
- Treat automation as evidence, not as proof that the system is secure.
- Record exceptions with an owner, rationale, compensating control, expiry date, and removal issue.

## Risk tiers

Classify before implementation. Escalate when uncertain.

| Tier   | Typical change                                                                                                                                                                | Required gate                                                                                                                                   |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Low    | Copy, isolated UI, internal refactor, or tests with no data, dependency, privilege, or trust-boundary change                                                                  | Acceptance test, deterministic checks, self-review                                                                                              |
| Medium | API behavior, ordinary persisted data, dependency/configuration change, external provider, or new background processing                                                       | Security checklist, targeted negative tests, dependency/configuration scan, independent agent review                                            |
| High   | Authentication, authorization, tenant isolation, secrets, sensitive data, payments, destructive actions, migrations, infrastructure exposure, cryptography, or AI/agent tools | Threat-model delta, abuse cases, independent security review, targeted security tests, rollout and rollback proof, explicit human authorization |

## Secure development lifecycle

Use [NIST SP 800-218, SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final) as the core secure-development vocabulary. Map project controls and evidence to its four practice groups: Prepare the Organization, Protect the Software, Produce Well-Secured Software, and Respond to Vulnerabilities. SSDF 1.2 is a draft and is not the baseline until finalized and deliberately adopted.

For each feature:

1. Identify assets, actors, data classes, trust boundaries, privileges, and failure impact.
2. Write security requirements and abuse cases beside functional acceptance criteria.
3. Choose secure defaults and minimize exposed surface, permissions, data, and dependencies.
4. Review authorization, validation, error behavior, logging, concurrency, and recovery paths.
5. Verify controls with deterministic tests and preserve concise evidence.
6. Feed incidents, vulnerabilities, and near misses back into controls and regression tests.

For application controls, use [OWASP ASVS 5.0.0](https://owasp.org/www-project-application-security-verification-standard/) Level 2 as the default target for all applicable requirements. Record non-applicable requirements and rationale. Use the OWASP Top 10 and API Security Top 10 as awareness lists, never as a substitute for ASVS verification.

## Application, API, and tenant controls

- Authenticate at the boundary and authorize every protected operation in the backend.
- Resolve tenant context from the authenticated user's current membership. Never trust a client-supplied `tenant_id` as authorization.
- Check resource ownership and tenant membership at query time. Test cross-tenant reads, writes, searches, exports, object IDs, and bulk operations.
- Include tenant identity in cache keys, jobs, events, storage paths, rate limits, logs, and idempotency keys. Reject missing or ambiguous tenant context.
- For shared-schema multi-tenant PostgreSQL, consider row-level security as defense in depth. Keep explicit service authorization and test both layers; never rely on RLS alone.
- Use short-lived, revocable sessions or tokens; rotate refresh credentials; protect recovery, invitation, and password-setup flows against replay and account enumeration.
- Validate structured input at the boundary, constrain outputs, use parameterized data access, and encode for the destination context.
- Apply least-privilege service identities, explicit CORS, CSRF protection where cookies authenticate, bounded request sizes, timeouts, rate limits, and safe retries.
- Sign and timestamp webhooks, reject replay, make handlers idempotent, and store delivery outcomes without leaking secrets.
- Return non-sensitive errors. Redact credentials, tokens, personal data, and tenant payloads from logs, traces, analytics, and exception tools.

## Threat-model delta

Maintain one lightweight system threat model. Update only the affected delta when a change adds or alters:

- a trust boundary, actor, privilege, data class, or tenant path;
- an external provider, public endpoint, asynchronous flow, upload, export, or webhook;
- authentication, authorization, secrets, payment, infrastructure, AI model, retrieval source, or executable tool.

Answer these questions for the delta:

1. What are we building, and what assets and boundaries change?
2. What can go wrong, including abuse, failure, and cross-tenant paths?
3. Which preventive, detective, and recovery controls address it?
4. How will tests and runtime evidence show the controls work?
5. What residual risk remains, who accepts it, and when is it reviewed?

Use the [OWASP Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html) for the method. Prefer small data-flow diagrams and abuse cases over long prose.

## Engineering security gates

- **Secrets:** scan commits and CI inputs; keep secrets out of source, images, build logs, and client bundles; retrieve them at runtime from an approved secret store; rotate on suspected exposure.
- **SAST:** scan changed and reachable code, triage findings in context, and add a regression test for confirmed flaws.
- **SCA:** lock dependencies, review new direct dependencies, scan source and release artifacts, and track reachable vulnerabilities and license policy.
- **IaC:** scan infrastructure and container definitions; detect public exposure, broad IAM, unencrypted storage, mutable tags, missing logging, and unsafe defaults.
- **Dynamic tests:** add targeted authorization, injection, replay, upload, webhook, race, and abuse tests when the surface exists.
- **Gate:** block confirmed exploitable Critical or High findings in changed or reachable code. Permit only a documented, time-bounded exception with compensating controls.

## Privacy minimum

- Inventory personal and sensitive data, purpose, source, processor, region, retention, and deletion path.
- Collect the minimum data needed. Restrict secondary use and analytics by default.
- Define access, correction, export, deletion, retention, backup expiry, and legal-hold behavior before collecting regulated data.
- Encrypt sensitive data in transit and at rest, restrict access by role and purpose, and audit privileged access.
- Redact or pseudonymize non-production data and telemetry. Never copy production data into development by default.
- Maintain processor/vendor records, incident contacts, and a tested notification decision path.

Use [NIST Privacy Framework 1.0](https://www.nist.gov/privacy-framework/privacy-framework) as the privacy risk vocabulary. Apply jurisdiction-specific legal requirements separately; this baseline is not legal advice.

## Software supply chain

- Target [SLSA 1.2 Build Level 2](https://slsa.dev/spec/v1.2/) for release artifacts: use a hosted build platform and generate authenticated provenance tied to the artifact digest.
- Generate an SPDX SBOM for every release. Target [SPDX 3.0](https://spdx.dev/use/specifications/); if tooling cannot emit it reliably, pin a supported SPDX version and record the deviation.
- Pin build inputs and actions, minimize build permissions, isolate untrusted contributions, and never expose release secrets to untrusted jobs.
- Build once, store an immutable artifact, verify digest/provenance before promotion, and deploy the same artifact through environments.
- Retain source revision, dependency lock, SBOM, provenance, scan results, approver, deployment, and rollback evidence for each release.

## Conditional profiles

Activate every applicable profile in addition to the core baseline.

| Profile    | Trigger                                                                     | Minimum controls and source                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ---------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cloud      | Any managed cloud resource                                                  | IaC-only changes, least-privilege identities, private-by-default data, encryption, audit logs, backup/restore test, budget and exposure alerts, drift detection; pin the provider's current security benchmark                                                                                                                                                                                                                                                                                       |
| Container  | Any containerized workload                                                  | Follow [NIST SP 800-190](https://csrc.nist.gov/pubs/sp/800/190/final); run as a non-root user, never privileged, avoid host sockets, drop capabilities, use read-only filesystems where possible, set resource limits, scan minimal pinned images, and inject secrets at runtime                                                                                                                                                                                                                     |
| AI/LLM     | Model inference, embeddings, RAG, or model-generated decisions              | Apply [NIST AI RMF 1.0](https://www.nist.gov/itl/ai-risk-management-framework), [NIST AI 600-1](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence), and applicable [OWASP LLMSVS 2.0](https://owasp.org/www-project-llm-verification-standard/LLMSVS-v2.0-en.html) L2 controls; treat model input/output as untrusted, isolate tenant retrieval, record provider retention, evaluate quality/safety, and bound latency and cost |
| Agentic AI | A model can call tools, change state, access secrets, or act asynchronously | Apply the [OWASP Agentic Top 10](https://genai.owasp.org/2025/12/09/owasp-genai-security-project-releases-top-10-risks-and-mitigations-for-agentic-ai-security/); allowlist scoped tools, validate parameters, minimize credentials and egress, require confirmation for sensitive actions, cap budgets/steps, preserve an audit trail, and provide revocation and a kill switch                                                                                                                     |
| Mobile     | Native or packaged mobile client                                            | Apply [OWASP MASVS 2.1.0 and MASTG](https://mas.owasp.org/MASVS/) with the appropriate testing profile; protect local storage, transport, platform interaction, authentication, code integrity, and privacy. Apply ASVS separately to its backend                                                                                                                                                                                                                                                    |

## Evidence record

For each Medium or High risk, record:

- risk and affected asset/boundary;
- control and authoritative source requirement;
- test or review method;
- evidence location, revision, tool version, and timestamp;
- result, exceptions, owner, and expiry;
- residual risk and explicit acceptance for High risk.

Keep evidence reproducible and close to code or release metadata. Store summaries and stable links, not secrets or unbounded raw logs.

## Claims

Say what was actually verified, for example: "designed against applicable OWASP ASVS 5.0.0 Level 2 requirements; internal evidence available." Never claim certification, compliance, audit passage, or conformance without the required independent assessment and documented scope. OWASP does not certify products or vendors.

## Pinned sources

- NIST SP 800-218 SSDF **1.1** (final, 2022)
- OWASP ASVS **5.0.0** (stable, 2025), Level 2 applicable target
- SLSA specification **1.2**, Build Level 2 target
- SPDX specification **3.0** target
- NIST Privacy Framework **1.0**
- NIST AI RMF **1.0**, NIST AI 600-1, and NIST SP 800-218A when AI applies
- OWASP LLMSVS **2.0** Level 2 when production AI applies
- OWASP MASVS **2.1.0** plus current MASTG when mobile applies
