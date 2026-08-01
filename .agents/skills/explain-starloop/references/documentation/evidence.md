# Evidence for implemented features

Starloop does not treat a feature name, documentation page, memory, issue, capsule, comment, or test
title as proof of current behavior.

Before explaining, extending, documenting, or diagnosing an existing feature, inspect its relevant
current implementation. Start from the executable path and follow only the callers, state,
persistence, configuration, consumers, tests, or runtime behavior needed to answer the user's
question safely.

Keep the investigation proportional:

- use documentation and memory to locate evidence, then compare them with the current checkout;
- treat tests as intended or protected behavior, not automatically as observed runtime behavior;
- run runtime proof when it materially changes the answer;
- stop once the claim is supported or the remaining uncertainty is clear;
- explain evidence, contradictions, and uncertainty naturally rather than forcing fixed labels.

With active Crew, Atlas uses read-only Scout when the trace is substantial enough to benefit from
delegation. Scout returns precise paths and evidence but cannot make product, architecture,
security, scope, or release decisions. Atlas validates material evidence and owns the conclusion.
Atlas or Forge performs checks requiring writes, mutable services, or broader tools. A quick local
lookup may remain with Atlas.
