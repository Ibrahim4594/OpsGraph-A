# UI Design System

## Status

**Slug selected:** `dashboard` — pulled from the typeui.sh registry on 2026-04-27 ahead of the deferred UI milestone. Skill files live at:

- [`.claude/skills/design-system/SKILL.md`](../.claude/skills/design-system/SKILL.md) (Claude Code provider path — active)
- [`.agents/skills/design-system/SKILL.md`](../.agents/skills/design-system/SKILL.md) (universal mirror)

The UI Hold Gate is still in force: substantial dashboard component/layout work waits for explicit user go-ahead. M1 only records the selection so guidelines are in place when the UI milestone starts.

## Tooling

- **Design skill source:** `typeui.sh@0.7.0` (npm: `typeui.sh`, by bergside) — see [`./preflight-checklist.md`](./preflight-checklist.md) for install evidence.
- **Pull command used:** `npx typeui.sh pull dashboard -p claude-code -f skill`
  - Provider is `claude-code`, not `claude` (the upstream README is outdated on that point).
- **Component primitives (deferred):** shadcn/ui — set up in the UI milestone, not M1.
- **Styling (deferred):** Tailwind CSS v4.
- **Premium components (deferred):** `@21st-dev/magic`.

## Selection Rationale

`dashboard` is the literal match for an AIOps operator UI — its registry category is "Professional & Corporate" and its mission is exactly "modular grids, strong visual hierarchy, present complex data". Alternatives considered:

- `enterprise` / `professional` — too generic, no operator-dashboard specificity.
- `shadcn` — redundant with the manual shadcn baseline planned for the UI milestone.
- "Bold & Expressive" / "Morphism & Effects" categories — wrong tone for incident response (calm, trustworthy beats flashy).

## Design Tokens (from SKILL.md)

Authoritative source is [`.claude/skills/design-system/SKILL.md`](../.claude/skills/design-system/SKILL.md). Highlights:

- **Aesthetic:** Dark-themed cloud-platform (Heroku/Vercel/GitHub inspired), glass-like panels, soft shadows.
- **Typography:** IBM Plex Sans (primary, display, mono); scale `12 / 14 / 16 / 20 / 24 / 32`; weights 100–900.
- **Colors:**
  - `primary` `#0C5CAB`
  - `secondary` `#0a4a8a`
  - `success` `#10b981`
  - `warning` `#f59e0b`
  - `danger` `#ef4444`
  - `surface` `#09090b`
  - `text` `#fafafa`
- **Spacing:** 8pt baseline grid.

## Application Notes

- The dashboard milestone (final UI phase) must apply the `dashboard` skill consistently. The Tailwind v4 `@theme` block in `frontend/src/app/globals.css` will be derived from these tokens at that time.
- WCAG 2.2 AA defaults: focus-visible rings, keyboard nav, contrast-safe themes (the SKILL.md enforces this).
- Whenever the design intent is unclear, re-read [`.claude/skills/design-system/SKILL.md`](../.claude/skills/design-system/SKILL.md) rather than guessing.
