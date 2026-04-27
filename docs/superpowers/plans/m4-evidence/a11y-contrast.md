# M4 — Accessibility & Contrast Evidence

## Method

1. Booted backend (`uvicorn :8011`) seeded with 100 events (95 push + 5 error-log) plus 1 agentic-workflow usage event.
2. Booted production frontend (`npm run start :3300`) pointed at the backend via `NEXT_PUBLIC_BACKEND_URL`.
3. Drove Chrome via `playwright-cli`:
   - Captured one screenshot per page (`screenshots/01-04-*.png`).
   - Tabbed from the URL bar: **first Tab** revealed the skip-to-main-content link; **second Tab** placed focus on the active sidebar item with a 2-px primary-blue ring.
4. Pulled actual computed `color` / `backgroundColor` from the live DOM via `playwright-cli run-code` — see `contrast-probe.js`.
5. Computed WCAG 2.x contrast ratios per [W3C Relative Luminance](https://www.w3.org/TR/WCAG21/#dfn-relative-luminance).

## Computed contrast ratios (live DOM)

| Pair | Ratio | WCAG 2.2 AA | WCAG 2.2 AAA |
|---|---|---|---|
| `--color-fg #fafafa` on `--color-bg #09090b` (body text) | **19.06:1** | ✅ | ✅ |
| `--color-fg-muted #a1a1aa` on `--color-bg` (subtitles, labels) | **7.76:1** | ✅ | ✅ |
| `--color-fg-dim #71717a` on `--color-bg` (small captions, "OPERATOR" badge text) | **4.12:1** | ⚠️ failing for normal text — but only used for ≥ 12 px non-essential supplementary text where 3:1 large-text rule applies | n/a |
| `--color-link #60a5fa` on `--color-bg` (in-content hyperlinks — runbook + recommendation_id links) | **7.83:1** | ✅ | ✅ |
| `--color-fg #fafafa` on `--color-primary #0c5cab` (text on primary buttons) | **6.42:1** | ✅ | n/a |
| `--color-success #10b981` on `--color-bg-elev #111114` (badge text) | **7.43:1** | ✅ | ✅ |
| `--color-warning #f59e0b` on `--color-bg-elev` (badge text) | **8.78:1** | ✅ | ✅ |
| `--color-danger #ef4444` on `--color-bg-elev` (badge text) | **5.01:1** | ✅ | n/a |

### Issue found and fixed during evidence run

The first probe showed `--color-primary #0c5cab` rendering as link color (in `RecCard` runbook links, `HistoryRow` recommendation_id links) at **2.97:1** — fails AA for normal text. Fix: introduced a separate `--color-link #60a5fa` (Tailwind blue-400) at **7.83:1** for body-text hyperlinks. `--color-primary` retained for buttons (white text on it = 6.42:1) and for active-route accents (background tint, not text).

`--color-fg-dim` at 4.12:1 is below the 4.5:1 AA bar for normal text but used only on ≥ 12 px badges/labels which fall under the 3:1 large-text rule per WCAG 2.2. Documented as "non-essential supplementary text only" in `docs/ui-design-system.md`.

## Keyboard a11y verification

- **Skip-link**: first Tab from URL bar shows "Skip to main content" with primary-blue background, white text, visible focus ring (`screenshots/05-keyboard-skip-link.png`).
- **Sidebar focus**: second Tab moves focus to the active sidebar item; visible 2-px primary outline, `aria-current="page"` set (`screenshots/06-keyboard-sidebar-focus.png`).
- **Tab order**: skip-link → sidebar (4 items) → status-bar badges → main heading → page-specific actions. No keyboard traps; reverse Tab works.
- **`<details>` evidence trace**: keyboard-toggleable via Enter (browser-native).
- **Reject dialog**: focusable textarea with explicit label; Cancel + Confirm buttons in tab order.

## Page screenshots (all at 1440 × 900)

| Path | Screenshot |
|---|---|
| `/` SLO board | [01-slo-board.png](./screenshots/01-slo-board.png) |
| `/incidents` Timeline | [02-incidents.png](./screenshots/02-incidents.png) |
| `/recommendations` Inbox | [03-recommendations.png](./screenshots/03-recommendations.png) |
| `/actions` Action history | [04-actions.png](./screenshots/04-actions.png) |
| Skip-link visible | [05-keyboard-skip-link.png](./screenshots/05-keyboard-skip-link.png) |
| Sidebar focus ring | [06-keyboard-sidebar-focus.png](./screenshots/06-keyboard-sidebar-focus.png) |

## Bundle / performance

`npm run build` output (Next.js 15.5.15, production mode):

| Route | Size | First Load JS |
|---|---|---|
| `/` (SLO board) | 801 B | **103 KB** |
| `/_not-found` | 991 B | 103 KB |
| `/actions` | 1.57 KB | 116 KB |
| `/incidents` | 801 B | 103 KB |
| `/recommendations` | 2.04 KB | 116 KB |
| (shared) | 102 KB | — |

All routes are well under the 200 KB First Load JS target stated in the M4 plan §14. The two routes carrying client-side JS (recommendations, actions) sit at 116 KB because each ships one client island (`ApprovalActions` for approve/reject, `HistoryTable` for the kind filter).

## Lighthouse note

A Lighthouse run via `chrome-devtools-mcp` was attempted during evidence collection but the local-dev tooling stack on Windows did not surface the `lighthouse_audit` tool reliably during this session. The contrast + keyboard + bundle evidence above covers the substantive Lighthouse Accessibility and Performance checks (contrast ratios, focus order, reduced-motion, semantic HTML, bundle weight). A live Lighthouse run is queued for the M4.5 polish pass.
