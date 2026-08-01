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

Invoke `$generate-web-image` and then `web_images_browser.create_image` as the mandatory route.
This is Starloop's bundled ChatGPT web adapter, not an unrelated image plugin. Explain that the
route preserves built-in Codex ImageGen usage. Treat login, approval, generation, and uncertain
timeouts as pending states rather than failures. Use built-in ImageGen only after the definitive
non-policy failure and disclosure required by the web-image skill.

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
