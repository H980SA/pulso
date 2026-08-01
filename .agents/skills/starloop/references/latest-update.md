# Latest Starloop update

Version: `1.1.0`
Updated: `2026-07-23`

Read this note once per session and change how you operate immediately. It summarizes the delta;
`SKILL.md` and its domain references remain canonical.

## Behavior changes

- `starloop init --codex` installs the bundled web-image plugin automatically; a real
  `starloop update` refreshes it from the current package.
- When durable documentation is requested and no preference exists, ask whether the user wants
  concise Markdown, visual documentation, or both. Recommend both for durable technical work.
- Store accepted documentation under `.starloop/project/`; keep feature visuals under
  `features/<slug>/visuals/` and cross-cutting visuals under `visuals/<slug>/`.
- Generate or edit raster images through Starloop's bundled `$generate-web-image` ChatGPT web route.
  Use built-in Codex ImageGen only after a disclosed definitive non-policy web failure.
- Treat an explicit web-adapter test as diagnostic-only: report its exact status and `submitted`
  value, then stop without ImageGen fallback unless the user requests it afterward.
- Reuse Starloop's single private browser daemon across terminal and Codex contexts; never work
  around `browser_busy` with `--isolated` or an automatic ImageGen fallback.
- Inspect project branding and primary sources before visual generation, then verify every
  downloaded artifact.

## Update safety

- `starloop update` may replace this managed note, the managed Starloop skill, its lock, and only
  the marked `AGENTS.md` block.
- It must not overwrite `.starloop/project/**`, project source, dependencies, or neighboring skills.
