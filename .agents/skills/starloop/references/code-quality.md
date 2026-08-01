# Code quality and maintainable boundaries

Optimize for code that a new maintainer can locate, change, test, and remove safely. Treat line
count as an early warning, not as an architecture method.

## Apply the size guardrail

- Prefer small cohesive handwritten modules; many will naturally remain below 250 logical lines,
  but do not make that a target.
- Before extending a file near 300 logical lines, stop and review its responsibilities,
  dependencies, public surface, and reasons to change.
- Fail the deterministic gate above 400 logical lines. Count executable/declarative lines while
  ignoring blank lines and comment-only lines when tooling supports it.
- Exclude only generated output, lockfiles, immutable migrations, or unusually large declarative
  schemas and fixtures. Scope every exclusion to the file or pattern and record why it is safe.
- Apply stricter limits when the repository or language already defines them.

## Split on a real boundary

Extract a module only when its name and ownership become clearer. Prefer boundaries such as:

- one domain or use case;
- public contract versus private implementation;
- validation and parsing versus execution;
- orchestration versus provider or persistence adapters;
- policy and deterministic rules versus I/O;
- UI composition versus state, data access, or independently meaningful components.

Give each extracted module a narrow public API and a clear dependency direction. Keep behavior
that changes together close together. Do not create arbitrary numbered chunks or catch-alls named
`utils`, `helpers`, `common`, `manager`, or `service` without a precise owning concept.

Do not fragment code into one-function files or wrappers that merely forward a call. A shorter file
is not cleaner when navigation, coupling, or indirection increases.

## Leave the touched surface clean

- Delete dead branches and commented-out implementations; history belongs in version control.
- Remove unused imports, exports, dependencies, flags, and stale comments within scope.
- Consolidate duplicated business rules behind a named owner only after proving they are the same
  rule, not merely similar code.
- Keep comments focused on intent, constraints, or non-obvious tradeoffs. Let names and structure
  explain what the code does.
- Fix warnings at their source. Do not add broad linter/type suppressions, skipped tests, or empty
  error handling to make a gate green.
- Record unavoidable debt with its reason, risk, owner, removal condition, and bounded follow-up;
  do not leave anonymous `TODO` or `FIXME` markers.

## Detect decomposition pressure early

Review the design when any of these signals appears, even below the line threshold:

- the file exposes several unrelated concepts;
- groups of functions use different dependency clusters;
- tests require unrelated setup or change for unrelated behavior;
- the file is a frequent merge-conflict hotspot;
- a new feature adds another conditional mode instead of a named policy;
- the filename or explanation needs “and” to describe its job;
- extraction would break a circular dependency or clarify ownership.

Keep functions at one abstraction level. Extract nested rules or independently testable policy,
not every long-looking block. Prefer explicit names and direct code over speculative abstractions.

## Refactor without hiding behavior changes

1. Inspect callers, tests, ownership, and dependency direction.
2. Add characterization tests first when current behavior is not already protected.
3. Select one coherent boundary and state why it owns the extracted behavior.
4. Preserve the public contract unless the approved feature explicitly changes it.
5. Move one boundary at a time, remove dead exports, and run targeted checks after each move.
6. Run the repository's complete local gate before delivery.

Separate a substantial behavior-preserving extraction from feature logic when combining them would
make review or rollback ambiguous. Keep tiny local cleanup in the same coherent change.

## Automate and review

Use the stack's deterministic tooling for the hard ceiling, such as ESLint `max-lines` for
JavaScript/TypeScript or an equivalent repository-native check. Do not introduce a second tool when
the existing linter can enforce the rule. Revalidate tool behavior against its current official
documentation; the threshold is a repository policy, not a universal measure of good design.

During review, verify that the change improves or preserves code health, tests cover the affected
contract, module names reveal ownership, dependencies point inward, and no new catch-all or circular
dependency was introduced. Report exceptions and residual maintainability debt explicitly.
