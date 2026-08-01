# Models and metrics

Roles are independent from models:

```text
role = authority and operating contract
model = inference engine for the current session
effort = reasoning budget for subsequent turns
```

Atlas inherits the user's live provider selection. Forge and Scout receive configurable economical
defaults. `/model` changes one live session and never changes its role. An explicit project setting
changes future defaults.

Starloop records values available from provider lifecycle hooks and a bounded structural tail of
the current provider transcript per turn and member. It extracts usage records without loading
conversation text into another model:

- input, cached input, output, and reasoning tokens;
- model and effort;
- elapsed turn time and Crew wall-clock time;
- task completion, failure, stall, recovery, and strong allowance events;
- observed allowance or account-percentage changes when exposed.

An observed one-percent account drop is a strong event, not guaranteed causal attribution when the
same account is used elsewhere. Starloop labels that distinction.

`starloop crew benchmark` compares direct Atlas and Crew totals from those observed values. Quality,
escaped defects, repairs, and acceptance evidence remain project evidence; Starloop does not invent
them from token data. Token reduction is never reported as a quality improvement by itself.
