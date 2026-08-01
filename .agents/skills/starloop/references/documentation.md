# Documentation

Make durable documentation concise, source-grounded, and easy to consume in the form the user
actually prefers.

## Set the delivery mode

When documentation is in scope and the user has not already chosen a format, ask one question in
the user's language before authoring:

> How do you want to consume this documentation: concise text (`.md`), visual documentation
> (modern infographics), or both?

Offer exactly these modes:

1. **Concise text**: searchable, diffable Markdown is the primary explanation.
2. **Visual**: infographics are the primary explanation. Keep only a minimal `sources.md` for
   citations, generation provenance, and accessible descriptions; do not duplicate the narrative.
3. **Both**: concise Markdown is canonical and a matching infographic series provides the fast
   visual route.

Recommend both for durable product, architecture, security, or operational documentation because
the Markdown remains maintainable while the visuals shorten onboarding. Do not ask again when the
choice is explicit in the current request or already recorded in the owning feature capsule.

## Script onboarding before illustrating it

Treat onboarding as a sequential learning experience, not a catalog of features. Before generating
raster:

1. Define the novice reader, what they know, and what they must be able to do afterward.
2. Write and pass through the human gate a complete text script. If the sequence is not clear
   without imagery, it is not ready for imagery.
3. Introduce every product term before first use. Define the purpose, user action, automatic system
   behavior, resulting artifact, and next step for each frame.
4. Use one running example across the sequence so each frame advances the same story. Do not change
   metaphor, domain, or example merely for visual variety.
5. Explain the product's motivation and limitations before implementation details. Never imply
   automatic quality, security, token, time, or cost improvement when the system only enables and
   measures it.
6. Separate the ordered onboarding from a lookup-oriented reference library. Label the reference
   pages as non-sequential and organize them by the reader's question or moment of need.
7. Give sequential frames a stable orientation pattern such as `why`, `you`, `system`, `result`,
   and `next`. Prefer comprehension over decorative density.

Do not accept a generated onboarding because it is polished, consistent, or information-dense.
Inspect whether a novice can explain the flow, vocabulary, choice points, outputs, and next action
without relying on outside prose.

## Give every visual a job

Write a one-sentence purpose contract before prompting for any visual document:

> For `[reader]` who needs to answer `[question]`, this visual makes `[relationship or sequence]`
> faster to understand so they can `[decision or next action]`; truth is checked against
> `[canonical source or evidence]`.

A visual passes only when all five fields are real and specific. If there is no reader question,
relationship, decision, or next action, it is decoration rather than documentation. Keep it out of
the accepted documentation set.

- Make the title the reader's actual question, not a feature name without context.
- Show why the information matters before showing internal mechanics.
- Label analogies with the exact product concepts they explain; never ask the reader to infer the
  mapping from a pretty metaphor.
- Use exact commands, ownership, limits, and outputs. Omit uncertain detail instead of filling
  space.
- End sequential frames with the next action. End reference frames with when to use them and the
  evidence they should leave.
- Test comprehension with a representative novice: they should identify the question, explain the
  relationship, choose the next action, and name the source of truth without coaching.

## Keep every artifact inside Starloop project state

Use project-owned paths; `init` and `update` must never manage or overwrite them:

```text
.starloop/project/
├── docs/<slug>.md
├── visuals/<slug>/
│   ├── 01-overview.png
│   └── sources.md
├── features/<slug>.md
└── features/<slug>/visuals/
    ├── 01-overview.png
    ├── 02-flow.png
    └── sources.md
```

Use `features/<slug>/visuals/` when the images explain one feature and `visuals/<slug>/` for
product-wide or cross-cutting material. Use ordered, stable filenames so readers can follow the
story without opening Markdown first. Keep drafts or adapter experiments under `artifacts/`, not
beside accepted project documentation.

## Build visual documentation through the bundled adapter

Invoke Starloop's bundled web-image skill as the mandatory route: `$generate-web-image` in Codex or
`/chatgpt-web-images:generate-web-image` in Claude Code. It resolves the provider-specific
`create_image` tool and is part of Starloop, not an unrelated image plugin. In Codex, explain that
the route preserves built-in ImageGen usage; in Claude Code, explain that it adds raster generation
through the user's ChatGPT subscription. Treat login, generation, and uncertain timeouts as pending
states. Follow the web-image skill's provider-specific definitive-failure policy.

Before generating:

1. Extract the factual spine, intended reader, decisions, sequence, and terms that must remain
   verbatim.
2. Inspect project tokens, logos, fonts, UI screenshots, accepted visual references, and existing
   documentation. Prefer exact project assets over inferred branding.
3. Map every material external claim to a primary source. Assign stable source numbers before
   prompting; never invent citations inside the image.
4. Choose the smallest useful visual sequence. Use one infographic for one coherent mental model;
   split only when legibility or causal order requires it.
5. Write a precise prompt with title, hierarchy, diagram relationships, palette, typography,
   dimensions, exact text, source markers, and elements that must not be copied from references.
6. Attach at most four ordered references and state each role explicitly. A useful order is:
   layout language, exact logo, palette or UI system, and subject reference.
7. Set `output_dir` to the owning `.starloop/project/**/visuals/` directory. Use `count` from one to
   eight only for a same-turn series requested from one prompt.

Treat a reference infographic as layout and density guidance, not as content to imitate. Preserve
the project's own logo, color system, naming, and technical truth.

## Keep the visuals useful and trustworthy

- Prefer high visual information density with a clear reading path, strong hierarchy, short labels,
  diagrammatic relationships, generous whitespace, and a restrained project palette.
- Do not render paragraphs into images. Move nuance, caveats, and long definitions to Markdown or
  the source ledger.
- Include document title, sequence number, version or date when facts may drift, and compact source
  markers near the claims they support.
- Keep clickable URLs, retrieval dates when relevant, and image-to-source mappings in `sources.md`.
- Add a concise accessible description for every image in `sources.md`, even in visual-only mode.
- Never present generated diagrams as runtime evidence. Label conceptual, proposed, and observed
  states accurately.

Inspect every downloaded image before accepting it. Verify spelling, exact project names, factual
relationships, source markers, numbering, cropping, contrast, logo fidelity, and cross-image
consistency. Regenerate or edit only after the prior tool call has reached a definitive terminal
state.
