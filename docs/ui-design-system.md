# UI Design System (M4 Finalized)

## Status

**Lifted UI Hold Gate on 2026-04-27.** The operator dashboard ships with the `dashboard` typeui.sh skill applied throughout. This document records the rationale, the actual tokens used in the codebase, and the QA checklist for any future UI change.

- **Skill source of truth:** [`.claude/skills/design-system/SKILL.md`](../.claude/skills/design-system/SKILL.md) — Claude Code provider, active.
- **Token implementation:** [`frontend/src/app/globals.css`](../frontend/src/app/globals.css) — semantic CSS custom properties + Tailwind 4 `@theme` block.
- **Component primitives:** hand-written shadcn-style components under [`frontend/src/components/ui/`](../frontend/src/components/ui/) (Card, Badge, Button, EmptyState).

## Why `dashboard`?

The `dashboard` slug is the literal match for an AIOps operator UI — its registry category is "Professional & Corporate" and its mission is "modular grids, strong visual hierarchy, present complex data." Alternatives considered and rejected:

- `enterprise` / `professional` — too generic; no operator-tool specificity.
- `shadcn` — redundant with the shadcn baseline we already pull in.
- "Bold & Expressive" / "Morphism & Effects" categories — wrong tone for incident response (calm + trustworthy beats flashy).

## Design tokens

| Role | Value | Token |
|---|---|---|
| Surface | `#09090b` | `--color-bg` |
| Surface (elevated) | `#111114` | `--color-bg-elev` |
| Surface (highest) | `#18181b` | `--color-bg-elev-2` |
| Foreground | `#fafafa` | `--color-fg` |
| Foreground (muted) | `#a1a1aa` | `--color-fg-muted` |
| Foreground (dim) | `#71717a` | `--color-fg-dim` |
| Primary | `#0c5cab` | `--color-primary` |
| Primary (hover) | `#0a4a8a` | `--color-primary-hover` |
| Primary (soft) | `rgba(12,92,171,0.12)` | `--color-primary-soft` |
| Success | `#10b981` | `--color-success` |
| Warning | `#f59e0b` | `--color-warning` |
| Danger | `#ef4444` | `--color-danger` |
| Border | `#1f1f23` | `--color-border` |
| Border (strong) | `#27272a` | `--color-border-strong` |
| Radius | `12px` / `8px` | `--radius` / `--radius-sm` |
| Grid | `8px` baseline | `--grid` |

**Typography**: IBM Plex Sans loaded via `next/font/google` (300 / 400 / 500 / 600 / 700) into `--font-ibm-plex` and re-exported as Tailwind's `--font-sans`. Scale: `12 / 14 / 16 / 20 / 24 / 32 px`.

## Component states (required for every interactive component)

| State | Visual treatment |
|---|---|
| `default` | Token-based bg + fg per role |
| `hover` | One step up the elevation ladder OR primary-hover for primary actions |
| `focus-visible` | 2 px primary outline at 2 px offset (global rule in `globals.css`) |
| `active` | Same as hover or one step deeper |
| `disabled` | `opacity: 0.5` + `cursor: not-allowed` |
| `loading` | Disabled state + label switch ("Approve" → "Working…") |
| `error` | Inline `role="alert"` text, danger token, never blocks navigation |

## Accessibility (WCAG 2.2 AA — testable)

- **Skip link** at the top of every page (`<a href="#main">`), styled to appear on focus only.
- **Focus indicator** is global; never hidden via `outline: none` without an equivalent replacement.
- **Touch targets** ≥ 44 × 44 px for all interactive elements (Sidebar items, StatusBar badges, page buttons all sized via Button md = 44 px high).
- **Semantic HTML first**: `nav`, `main`, `ol > li` for the timeline, `table` with `th[scope]` for action history. ARIA only as supplement (`role="status"` on SLO cards, `role="dialog"` on the reject reason panel).
- **Reduced motion**: `@media (prefers-reduced-motion: reduce)` clamps all transitions to ≤ 0.01 ms in `globals.css`.
- **Contrast** (verified, see `m4-evidence/a11y-contrast.md`):
  - `--color-fg` on `--color-bg`: ≥ 18:1 (AAA)
  - `--color-fg-muted` on `--color-bg`: ≥ 7:1 (AAA)
  - `--color-primary` on `--color-bg`: ≥ 4.5:1 (AA normal text)

## Writing tone

Concise · confident · helpful · clear · friendly · professional · action-oriented · low-jargon. Never use exclamation marks in dashboard copy — a calm tone is the rule for an incident-response context.

## Anti-patterns

- ❌ Bare hex values inside components (always go through tokens).
- ❌ `outline: none` without a visible replacement.
- ❌ Decorative motion without purpose (drift, pulse, parallax — none of these belong in an operator console).
- ❌ Multiple visual metaphors (don't mix glass + flat + skeuomorphic).
- ❌ Inaccessible hit areas (< 44 × 44 px) on touch-eligible interactives.
- ❌ Free-text alongside structured badges where a badge would do.

## QA checklist (run before merging any UI change)

- [ ] All new colors come from tokens; grep `#[0-9a-f]{3,6}` in `frontend/src/components/**` returns zero results outside of comments.
- [ ] Every interactive element has the seven states above (or an explicit reason in the PR).
- [ ] Keyboard tab path is logical: skip → sidebar → status → main content → page-specific actions.
- [ ] Focus indicator is visible on every focusable element (visual check + Playwright screenshot in `m4-evidence/`).
- [ ] vitest passes, `npm run typecheck` passes, `npm run lint` passes, `npm run build` finishes with no warnings.
- [ ] Lighthouse Accessibility score ≥ 95 on each of the four pages.
- [ ] First Load JS for any single route < 200 KB.

## Migration notes

This is the first UI milestone. There is no legacy UI to migrate from. Future M4.x / M6 changes that touch tokens should:

1. Update [`globals.css`](../frontend/src/app/globals.css) (the single source of CSS variables).
2. Re-run the contrast spot-checks against `--color-bg` / `--color-bg-elev` and update `m4-evidence/a11y-contrast.md`.
3. Re-run Lighthouse against all four pages and update the evidence files.

## References

- [`.claude/skills/design-system/SKILL.md`](../.claude/skills/design-system/SKILL.md) — the source skill.
- [`docs/runbooks/`](./runbooks/) — the per-action-category operator runbooks linked from the recommendations inbox.
- [`adr/ADR-004-approval-gate-model.md`](../adr/ADR-004-approval-gate-model.md) — state machine the approval-gate UX implements.
- [`plans/milestone-4-execution-plan.md`](../plans/milestone-4-execution-plan.md) — full M4 plan that produced this UI.
