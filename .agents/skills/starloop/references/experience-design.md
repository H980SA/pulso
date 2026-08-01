# Experience Design

Design user-facing work from tasks and states before choosing an aesthetic.

## Run the experience loop

1. Define the user, context, task, current workaround, desired outcome, constraints, and measurable success.
2. Map entry, action, system response, visible feedback, transition, recovery, and exit.
3. Cover loading, empty, partial, success, error, timeout, offline, permission, expired-session, destructive, and long-content states as relevant.
4. Start with established, researched patterns. Adapt or create only when evidence shows they do not fit.
5. Explore visual directions only after the task and state model is coherent.
6. Select one direction and state what to borrow, why it supports the task, what not to copy, and any provenance or licensing constraint.
7. Write a concise brief and implement with semantic components and tokens.
8. Validate in the browser, with accessibility checks, visual evidence, and representative users; iterate on observed failure.

## Use raster generation selectively

Use raster generation when visual uncertainty is material:

- Explore distinct art directions, moodboards, composition, materials, color, texture, illustrations, hero imagery, or bitmap assets.
- Generate a small number of intentionally different directions from the same approved task constraints.
- Use a few references and describe purpose, spatial relationships, fixed elements, and prohibited imitation.

When raster generation is appropriate, invoke Starloop's bundled web-image skill as the mandatory
default route: `$generate-web-image` in Codex or
`/chatgpt-web-images:generate-web-image` in Claude Code. Follow its login, completion, download,
and batch rules. In Codex, explain that ChatGPT web preserves built-in ImageGen usage; in Claude
Code, explain that the plugin supplies raster generation through the user's ChatGPT subscription.
A missing or disabled plugin is a setup state, not a definitive generation failure. Waiting for
login, generation, or an uncertain result is not a failure. Codex may use built-in ImageGen only
after a definitive non-policy web failure, with disclosure before fallback; Claude Code must stop
and report that failure because it has no bundled raster fallback. Never bypass a safety refusal.
For an explicit adapter test, report the exact web status and `submitted` value, then stop.

When the raster is durable documentation rather than design exploration, load
`references/documentation.md` from the Starloop skill and follow its format choice, project-owned
paths, source ledger, branding, and visual verification contract.

Skip raster generation when the need is exact interaction, responsive layout, a dense form or
table, component behavior, design tokens, accessibility, an icon or logo system, vector output, or
pixel-accurate production UI. Use code, browser prototypes, or a design tool instead. Never treat a
generated raster as the implementation specification.

## Define the brief and tokens

- Include user goal, task flow, information hierarchy, content, component and state inventory, responsive behavior, accessibility target, visual direction, success metric, and non-goals.
- Organize tokens as primitive values, semantic intent, and component tokens only when a component needs a stable exception.
- Cover color, typography, spacing, size, radius, border, elevation, motion, opacity, and interaction states.
- Make semantic tokens the component API. Do not scatter raw visual values through product code.
- Use the stable [Design Tokens Format Module 2025.10](https://www.designtokens.org/TR/2025.10/format/) when interoperability adds value. Describe it accurately as a final community report, not a W3C Standard.

## Evolve the interface system

Treat consistency as predictable meaning and behavior, not visual sameness. Preserve agent judgment
with this decision protocol:

1. Inspect existing tokens, primitives, patterns, domain components, usages, states, tests, and any
   component catalog before creating or styling another component.
2. Reuse an existing component when intent, semantics, behavior, and states match. Do not reuse it
   merely because two surfaces look similar.
3. Extend a shared primitive or pattern only when the new variant is general, stable, and coherent
   with its public contract.
4. Keep business language and behavior in the owning domain. Keep uncertain visual experiments
   local until evidence establishes a reusable pattern.
5. Treat a change to global hierarchy, interaction language, or brand expression as a material
   design decision and pass it through the human gate. Make routine, reversible composition choices
   autonomously.
6. Verify semantics, content, keyboard and focus behavior, every meaningful state, responsive use,
   and visual drift at the narrowest reliable level.

- Layer the system as foundations and tokens, UI primitives, reusable interaction patterns, domain
  components, and feature-local composition. Do not turn a global `shared` folder into a catch-all.
- Name variants by semantic intent such as `primary`, `secondary`, `quiet`, or `danger`, not by a
  color, screen, campaign, or temporary aesthetic.
- Give reusable components a bounded contract: when to use and not use, content rules, variants,
  states, semantics, accessibility, responsive behavior, and representative examples.
- Prefer controlled variants and composition over copied styles or arbitrary overrides. Do not grow
  one mega-component that encodes unrelated domain modes.
- Do not promote a component after an arbitrary number of occurrences. Reuse frequency is evidence;
  shared meaning and behavior are the decision.
- Maintain an executable inventory with the repository's existing stories, examples, tests, or
  documentation when it pays for itself. Do not add Storybook or another catalog tool solely for
  ceremony.

Use [WCAG 2.2 consistent identification](https://www.w3.org/WAI/WCAG22/Understanding/consistent-identification)
and established component guidance such as the [GOV.UK button](https://design-system.service.gov.uk/components/button/)
as research anchors, not as a visual style to copy.

## Keep aesthetics subordinate to usability

- Treat glassmorphism, neomorphism, skeuomorphism, and every visual trend as a testable style hypothesis.
- Require the interface to remain understandable and operable without blur, shadow, texture, color alone, or decorative depth.
- For glass effects, provide a stable backing surface and verify contrast against every real background.
- For neomorphic effects, add explicit boundaries, focus, and state cues; do not make soft shadows the only affordance.
- For skeuomorphic effects, preserve labels, platform conventions, semantic controls, and familiar behavior; do not bake functional text into imagery.
- Budget blur, large shadows, animation, fonts, and imagery for rendering and network cost.

## Prove the experience

- Target WCAG 2.2 Level AA and record evidence; do not claim conformance from a scanner score.
- Use semantic HTML and native controls first. Add ARIA only when necessary and implement the complete keyboard and state contract.
- Automate useful checks, then manually inspect keyboard flow, focus, zoom, reflow, contrast, names, roles, values, errors, announcements, and relevant assistive technologies.
- Exercise critical tasks with real browser interaction, DOM and accessibility-tree inspection, console and network review, and screenshots across agreed viewports and states.
- Use visual regression to catch drift, not to decide usability.
- Ask representative users to complete realistic tasks without guidance. Measure completion, errors, recovery, time, confidence, and language; do not substitute preference polling for observation.
- Include disabled users and assistive-technology users when the product audience includes them.

Use [WCAG 2.2](https://www.w3.org/TR/WCAG22/), [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/practices/read-me-first/), [W3C accessibility evaluation guidance](https://www.w3.org/WAI/test-evaluate/), and [GOV.UK prototyping guidance](https://www.gov.uk/service-manual/design/making-prototypes) as primary references. Treat automated evaluation as assistance, not proof of accessibility.
