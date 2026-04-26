# Milestone 1 — Foundation (Backend-First Variant) — Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. TDD discipline (superpowers:test-driven-development) governs all production code: failing test FIRST, watch it fail, minimal code to pass, refactor, commit. Steps use checkbox (`- [ ]`) syntax for tracking.

## Scope Note (2026-04-27 — Revised)

**This is the backend-first M1 variant.** The original parent plan blends backend + frontend in M1; per user direction, frontend work is deferred until **after** M3 (AIOps core) and M5 (GitHub agentic workflows). New milestone order:

1. **M1 (this plan)** — Foundation, backend-only.
2. **M2** — Observability + SLO baseline.
3. **M3** — AIOps core (detection, correlation, recommendations).
4. **M5** — GitHub agentic workflows.
5. **M4** — UI / Operator Dashboard (uses the parked `dashboard` SKILL.md at `.claude/skills/design-system/SKILL.md`).
6. **M6** — Portfolio polish.

The dashboard design skill was pulled in advance (2026-04-27) so guidelines are ready when the UI phase opens; substantial UI buildout still respects the M4 Hold Gate.

## Goal

Stand up a deterministic, professional repo skeleton for the **backend** AIOps service — FastAPI app + settings model + health endpoint, base documentation (architecture, roadmap, security model, SLO stub, ADR-001), CI for the backend, and a complete preflight evidence log — so M2/M3 can move fast on top of a verified foundation.

## Architecture (Backend Only at M1)

`backend/` is a Python package (FastAPI + pydantic-settings, ruff/mypy/pytest, src layout). The frontend directory is **not created** in M1 — it will be scaffolded in the future Milestone F plan that consumes the dashboard SKILL.md. CI runs lint/typecheck/test for backend on `ubuntu-latest`. Docs and ADRs live at the repo root.

## Tech Stack

- **Backend:** Python 3.14, FastAPI, pydantic-settings, uvicorn, httpx (test client), pytest, ruff, mypy.
- **CI:** GitHub Actions (`ubuntu-latest`), `actions/setup-python@v5`.
- **Reserved (not used in M1):** `typeui.sh` dashboard SKILL.md (parked at `.claude/skills/design-system/SKILL.md`); `@21st-dev/magic`, Tailwind, shadcn — all gated to M4.

---

## File Structure (Final State After Milestone 1)

```
AIOPS/
├── .editorconfig
├── .gitignore
├── README.md
├── adr/
│   └── ADR-001-hybrid-architecture.md
├── docs/
│   ├── preflight-checklist.md
│   ├── architecture.md
│   ├── roadmap.md
│   ├── security-model.md
│   ├── slo-spec.md
│   ├── ui-design-system.md
│   └── runbooks/
│       └── README.md
├── backend/
│   ├── pyproject.toml
│   ├── README.md
│   ├── src/repopulse/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   └── api/
│   │       ├── __init__.py
│   │       └── health.py
│   └── tests/
│       ├── __init__.py
│       ├── test_config.py
│       └── test_health.py
├── infra/
│   └── README.md
├── plans/
│   ├── aiops-detailed-implementation-plan.md   (existing, untouched)
│   └── milestone-1-execution-plan.md           (this file)
├── .claude/
│   └── skills/
│       ├── design-system/SKILL.md              (parked dashboard skill)
│       └── playwright-cli/SKILL.md             (parked for M4 testing)
├── .agents/
│   └── skills/design-system/SKILL.md           (universal mirror of design system)
└── .github/
    └── workflows/
        └── ci.yml                              (backend-only)
```

Frontend (`frontend/`) and frontend-related directories are **intentionally absent in M1** and will appear in Milestone F.

---

## Task 1 — Repo Hygiene + First Commit

**Files:**
- Create: `.gitignore`
- Create: `.editorconfig`
- Create: `README.md` (initial seed; polished in Task 8)

- [ ] **Step 1: Write `.gitignore`**

```gitignore
# OS
.DS_Store
Thumbs.db

# Editors
.vscode/
.idea/
*.swp

# Python
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
dist/
build/

# Node (reserved for Milestone F)
node_modules/
.next/
out/
*.tsbuildinfo
playwright-report/
test-results/
.playwright/
.playwright-cli/

# Claude Code (machine-local)
.claude/settings.local.json

# Env
.env
.env.local
.env.*.local

# Tooling caches
.coverage
htmlcov/
```

- [ ] **Step 2: Write `.editorconfig`**

```editorconfig
root = true

[*]
end_of_line = lf
insert_final_newline = true
charset = utf-8
indent_style = space
indent_size = 2
trim_trailing_whitespace = true

[*.py]
indent_size = 4

[*.md]
trim_trailing_whitespace = false
```

- [ ] **Step 3: Write seed `README.md`**

```markdown
# RepoPulse AIOps

Production-grade AIOps reference project: observability, AI-assisted operations with guardrails, and measurable reliability outcomes. Backend-first development; operator UI lands at the end.

> Active milestone plans live in [`plans/`](plans/). High-level roadmap: [`plans/aiops-detailed-implementation-plan.md`](plans/aiops-detailed-implementation-plan.md). Current execution plan: [`plans/milestone-1-execution-plan.md`](plans/milestone-1-execution-plan.md).

## Repository Layout

- `backend/` — FastAPI service + AIOps core (Python 3.14)
- `infra/` — local Docker Compose + OTel collector (M2+)
- `docs/` — architecture, SLO spec, security model, runbooks
- `adr/` — Architecture Decision Records
- `.github/workflows/` — CI

The operator dashboard (`frontend/`) is deferred to a final UI milestone after the AIOps core is shipped.

## Status

| Milestone | Scope | Status |
|---|---|---|
| M1 | Backend foundation | In progress |
| M2 | Observability + SLO baseline | Planned |
| M3 | AIOps core (detection / correlation / recommendations) | Planned |
| M5 | GitHub agentic workflows | Planned |
| M4 | Operator UI (dashboard) | Planned (last) |
| M6 | Portfolio polish | Planned (last) |
```

- [ ] **Step 4: Stage and commit**

```bash
git add .gitignore .editorconfig README.md plans/milestone-1-execution-plan.md
git commit -m "chore: repo hygiene baseline (.gitignore, .editorconfig, README seed)"
```

Expected: commit succeeds; `git log --oneline` shows one commit.

---

## Task 2 — Documentation Skeleton + ADR-001

**Files:**
- Create: `docs/architecture.md`
- Create: `docs/roadmap.md`
- Create: `docs/security-model.md`
- Create: `docs/slo-spec.md` (stub; filled in M2)
- Create: `docs/ui-design-system.md`
- Create: `docs/runbooks/README.md`
- Create: `adr/ADR-001-hybrid-architecture.md`
- Create: `infra/README.md` (placeholder)

- [ ] **Step 1: Write `docs/architecture.md`** — copy the mermaid diagram from `plans/aiops-detailed-implementation-plan.md` lines 162-179 verbatim, plus a "Component Map" section listing each box with its responsibility (1-2 sentences each), and a "Trust Boundaries" subsection enumerating: external → ingest API, ingest → event bus, recommendations → action gate (human approval), action gate → GitHub. Add a "Build Order" note explaining that the backend pipeline (left side of the diagram) is built first; the dashboard (right side) lands in the final UI milestone.

- [ ] **Step 2: Write `docs/roadmap.md`** — list the 6 milestones with their goals and acceptance criteria, **in the new execution order** (M1 → M2 → M3 → M5 → M4 → M6), with a status column (M1 = in progress, others = planned). Link back to `plans/aiops-detailed-implementation-plan.md` as source of truth and link to `plans/milestone-1-execution-plan.md` for the active execution plan.

- [ ] **Step 3: Write `docs/security-model.md`** — sections: (a) Threat model (what we trust, what we don't); (b) Action gate principles (read-only by default, human approval for destructive ops); (c) Secret handling (env vars with `REPOPULSE_` prefix, never committed; lists which secrets each component will need); (d) GitHub agentic workflow boundaries (scoped tokens, no force-push, no merge to main without review). One short paragraph each.

- [ ] **Step 4: Write `docs/slo-spec.md`** stub — header + "STATUS: STUB — completed in Milestone 2" callout + the table headers we'll fill (SLI, target, window, burn-rate alert thresholds).

- [ ] **Step 5: Write `docs/ui-design-system.md`**

```markdown
# UI Design System

## Status
**Slug selected:** `dashboard` — pulled from the typeui.sh registry on 2026-04-27 ahead of the deferred UI milestone. Skill files live at:
- `.claude/skills/design-system/SKILL.md` (Claude Code provider path — active)
- `.agents/skills/design-system/SKILL.md` (universal mirror)

The UI Hold Gate is still in force: substantial dashboard component/layout work waits for explicit user go-ahead. M1 only records the selection so guidelines are in place when the UI milestone starts.

## Tooling
- **Design skill source:** `typeui.sh@0.7.0` (npm: `typeui.sh`, by bergside) — see `docs/preflight-checklist.md` for install evidence.
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
Authoritative source is `.claude/skills/design-system/SKILL.md`. Highlights:
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
- Whenever the design intent is unclear, re-read `.claude/skills/design-system/SKILL.md` rather than guessing.
```

- [ ] **Step 6: Write `docs/runbooks/README.md`** — one paragraph: "Operational runbooks land here from Milestone 2 onward (telemetry validation, alert triage, rollback procedures). Each runbook is a single markdown file named `<scenario>.md` and is linked from the eventual dashboard alongside the recommendation type that triggers it."

- [ ] **Step 7: Write `infra/README.md`** — one paragraph: "Local stack (Docker Compose, OpenTelemetry Collector config) lands here in Milestone 2. Empty for now to keep the repo layout in `plans/aiops-detailed-implementation-plan.md` honored."

- [ ] **Step 8: Write `adr/ADR-001-hybrid-architecture.md`**

```markdown
# ADR-001: Hybrid Architecture (Python Backend + Deferred Next.js Frontend)

- **Status:** Accepted
- **Date:** 2026-04-27
- **Deciders:** Project owner (Ibrahim)

## Context
RepoPulse AIOps must combine: (a) Python-native AIOps logic (anomaly detection, correlation, recommendations) where the data-science ecosystem is strongest; and (b) a modern, accessible operator dashboard with first-class TypeScript tooling and a strong UI component ecosystem. To prevent UI churn from blocking the AIOps core, the backend is shipped first and the dashboard comes after the AIOps logic is proven.

## Decision
Adopt a hybrid monorepo: `backend/` runs FastAPI (Python 3.14). A future `frontend/` (Next.js 15 App Router, TypeScript, Tailwind v4, shadcn/ui) will land in the dedicated UI milestone after M1-M5 backend work is complete. Communication between the eventual dashboard and the backend is HTTP/JSON. Event-bus and time-series store choices are deferred to Milestone 2.

## Alternatives Considered
1. **Python-only with server-rendered Jinja templates** — fastest to ship but loses the operator-grade UI quality the parent plan mandates (Tailwind + shadcn + 21st components in M4).
2. **Node-only with TypeScript on both sides** — uniform stack but weaker AI/data tooling for the AIOps core.
3. **Frontend in M1 alongside backend** — original parent-plan ordering. Rejected because UI work risks consuming attention from the AIOps logic during the most uncertain milestones (M3).

## Consequences
**Positive:** Best-of-breed tools per concern; clear blast-radius separation; CI runs the backend stack first and the frontend stack joins later in its own job.

**Negative:** Two language toolchains long-term; the operator UI is unavailable until late in the project (mitigated by `/healthz` + curl verification, OTel UIs in M2, and CLI tooling for M3/M5 demos).

**Follow-ups:** ADR-002 (event bus choice) and ADR-003 (timeseries store) in Milestones 2–3. ADR-004 (UI architecture) when the UI milestone begins.
```

- [ ] **Step 9: Stage and commit**

```bash
git add docs/ adr/ infra/README.md
git commit -m "docs: scaffold architecture, roadmap, security model, SLO stub, ADR-001"
```

Expected: commit succeeds; `ls docs/ adr/ infra/` shows all expected files.

---

## Task 3 — Preflight Checklist with Evidence

**Files:**
- Create: `docs/preflight-checklist.md`

This task documents what was already installed in the conversation prior to plan execution. No new installs.

- [ ] **Step 1: Write `docs/preflight-checklist.md`**

```markdown
# Preflight Checklist

This document verifies that the mandatory tools from `plans/aiops-detailed-implementation-plan.md` § "Mandatory Agent Skill and Toolchain Preflight" are installed and callable. Evidence captured from the install session on 2026-04-26 / 2026-04-27.

## 1. Superpowers (`obra/superpowers`)
- **Source:** https://github.com/obra/superpowers
- **Install method:** Claude Code plugin marketplace `claude-plugins-official`. Plugin restored from clean state via `git clone --depth 1 --branch v5.0.7 https://github.com/obra/superpowers.git` into `C:\Users\ibrah\.claude\plugins\cache\claude-plugins-official\superpowers\5.0.7\`.
- **Version:** v5.0.7
- **Commit SHA:** `1f20bef3f59b85ad7b52718f822e37c4478a3ff5` (matches dereferenced `refs/tags/v5.0.7`)
- **Manifest verified:** `plugin.json` parses; `name: superpowers`, `version: 5.0.7`.
- **Skills present:** brainstorming, dispatching-parallel-agents, executing-plans, finishing-a-development-branch, receiving-code-review, requesting-code-review, subagent-driven-development, systematic-debugging, test-driven-development, using-git-worktrees, using-superpowers, verification-before-completion, writing-plans, writing-skills.

## 2. Playwright CLI (`@playwright/cli`)
- **Source:** https://www.npmjs.com/package/@playwright/cli (per docs at https://github.com/microsoft/playwright-cli — package was relocated to `@playwright/cli`).
- **Install method:** `npm install -g @playwright/cli@latest` then `playwright-cli install --skills` from repo root.
- **Version:** `0.1.9`
- **Binary path:** `C:\Users\ibrah\AppData\Roaming\npm\playwright-cli`
- **Project skills:** `.claude/skills/playwright-cli/SKILL.md` (+ `references/`)
- **Default browser detected:** Chrome.
- **Verification:** `playwright-cli --help` exits 0 and prints the documented command list (open, goto, snapshot, click, screenshot, etc.).
- **Reserved for:** browser-driven verification in the eventual UI milestone. Not used in M1.

## 3. Obsidian Skills (`kepano/obsidian-skills`)
- **Source:** https://github.com/kepano/obsidian-skills
- **Install method:** `npx -y skills add https://github.com/kepano/obsidian-skills.git -g -y --all` (CLI: `vercel-labs/skills` — npm `skills@1.5.1`).
- **Skills installed:** obsidian-markdown, obsidian-bases, json-canvas, obsidian-cli, defuddle (5 skills).
- **Source path:** `C:\Users\ibrah\.agents\skills\<skill>` (symlinked to `C:\Users\ibrah\.claude\skills\`).
- **Risk assessments (from CLI output):** obsidian-markdown=Safe; obsidian-bases=Low; json-canvas=Low; obsidian-cli=Med (Gen); defuddle=Med (Snyk). Med-risk skills only activate when explicitly invoked.

## 4. Awesome Design Skills (`bergside/awesome-design-skills` → `typeui.sh`)
- **Status:** CLI cached + `dashboard` slug pulled.
- **Source:** https://github.com/bergside/awesome-design-skills (npm package: `typeui.sh@0.7.0`).
- **Install method:** `npx -y typeui.sh` — cached at `C:\Users\ibrah\AppData\Local\npm-cache\_npx\1d023e8bfdadd56a\node_modules\typeui.sh\`.
- **Verification:** `node <cache>/typeui.sh/dist/cli.js --help` exits 0 and lists commands `generate, update, pull <slug>, list, randomize`.
- **Skill pulled:** `dashboard` (2026-04-27) via `npx typeui.sh pull dashboard -p claude-code -f skill` → `.claude/skills/design-system/SKILL.md` (+ universal mirror at `.agents/skills/design-system/SKILL.md`, both 4.2KB, identical content, frontmatter `name: dashboard`).
- **Provider naming gotcha:** the public docs show `-p claude` but the CLI rejects that with `Unsupported providers: claude. Supported: ...claude-code...`. Use `claude-code`.
- **UI Hold Gate:** still in force. Skill is loaded so guidelines are ready for the deferred UI milestone.

## Phase 0 Compliance
The plan's Phase 0 strict order is satisfied:
1. ✅ Install skills/tools from official sources.
2. ✅ Invoke/verify skills/tools (commands above produce documented output).
3. ✅ Read implementation plan (`plans/aiops-detailed-implementation-plan.md`).
4. ⏭ Begin Milestone 1 work (this plan executes that step).

## Windows-Specific Notes
- User's PowerShell has script execution disabled, so `npx.ps1` fails. Use `cmd.exe /c npx ...` or run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` for direct PowerShell use. Bash (git-bash) and `node`-direct invocations work without changes.
- Docs target: any machine running Python ≥3.11. Local dev tested on Windows 11 Pro 10.0.26200 with Python 3.14.3 and Node v24.14.1 (Node retained for tooling — frontend stack will land in the deferred UI milestone).
```

- [ ] **Step 2: Stage and commit**

```bash
git add docs/preflight-checklist.md
git commit -m "docs: preflight checklist with toolchain evidence (M1)"
```

---

## Task 4 — Backend Project Scaffolding

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/README.md`
- Create: `backend/src/repopulse/__init__.py`
- Create: `backend/src/repopulse/api/__init__.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: Write `backend/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "repopulse"
version = "0.1.0"
description = "RepoPulse AIOps backend"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "httpx>=0.27",
  "ruff>=0.7",
  "mypy>=1.13",
]

[tool.hatch.build.targets.wheel]
packages = ["src/repopulse"]

[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N"]

[tool.mypy]
strict = true
python_version = "3.11"
files = ["src", "tests"]
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write `backend/README.md`**

````markdown
# RepoPulse Backend

FastAPI service hosting the AIOps core (ingest, anomaly detection, correlation, recommendations). Milestone 1 ships the health endpoint and settings model only.

## Bring-up

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn repopulse.main:app --reload --port 8000
curl http://localhost:8000/healthz
```

## Quality Gates

```bash
ruff check src tests
mypy
pytest
```

All three must exit 0 in CI.
````

- [ ] **Step 3: Create empty `__init__.py` files**

```bash
mkdir -p backend/src/repopulse/api backend/tests
: > backend/src/repopulse/api/__init__.py
: > backend/tests/__init__.py
```

(Note: `backend/src/repopulse/__init__.py` is created in Task 6 with the `__version__` line.)

- [ ] **Step 4: Create venv and install dev deps**

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/python -m pip install -e ".[dev]"
```

Expected: pip resolves and installs all dev deps; final line `Successfully installed ...`.

- [ ] **Step 5: Verify structure**

```bash
find backend -type f -not -path '*.venv*' -not -path '*__pycache__*' | sort
```

Expected output:
```
backend/README.md
backend/pyproject.toml
backend/src/repopulse/api/__init__.py
backend/tests/__init__.py
```

- [ ] **Step 6: Commit scaffolding**

```bash
git add backend/pyproject.toml backend/README.md backend/src backend/tests
git commit -m "feat(backend): scaffold pyproject, src layout, dev deps"
```

---

## Task 5 — Backend: Settings Model (TDD)

**Files:**
- Test: `backend/tests/test_config.py`
- Create: `backend/src/repopulse/config.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_config.py`:

```python
"""Settings model contract."""
from repopulse.config import Settings


def test_settings_default_app_name() -> None:
    s = Settings()
    assert s.app_name == "RepoPulse"


def test_settings_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REPOPULSE_APP_NAME", "TestApp")
    monkeypatch.setenv("REPOPULSE_LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.app_name == "TestApp"
    assert s.log_level == "DEBUG"


def test_settings_default_log_level() -> None:
    s = Settings()
    assert s.log_level == "INFO"


def test_settings_default_environment() -> None:
    s = Settings()
    assert s.environment == "development"
```

- [ ] **Step 2: Run the test — expect failure**

```bash
cd backend
.venv/Scripts/python -m pytest tests/test_config.py -v
```

Expected: 4 tests collected, all fail with `ModuleNotFoundError: No module named 'repopulse.config'` (or the module resolves but the `Settings` symbol is missing — either is an acceptable RED).

- [ ] **Step 3: Write minimal `backend/src/repopulse/config.py`**

```python
"""Application settings loaded from environment."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """RepoPulse runtime settings.

    Env vars use the prefix `REPOPULSE_` (e.g. REPOPULSE_LOG_LEVEL=DEBUG).
    """

    model_config = SettingsConfigDict(
        env_prefix="REPOPULSE_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "RepoPulse"
    environment: str = "development"
    log_level: str = "INFO"
```

- [ ] **Step 4: Run the test — expect pass**

```bash
.venv/Scripts/python -m pytest tests/test_config.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run typecheck and lint**

```bash
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m mypy
```

Expected: both exit 0 with no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/src/repopulse/config.py backend/tests/test_config.py
git commit -m "feat(backend): settings model with REPOPULSE_ env prefix (TDD)"
```

---

## Task 6 — Backend: Health Endpoint + App Wiring (TDD)

**Files:**
- Test: `backend/tests/test_health.py`
- Create: `backend/src/repopulse/__init__.py` (with `__version__`)
- Create: `backend/src/repopulse/api/health.py`
- Create: `backend/src/repopulse/main.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_health.py`:

```python
"""Health endpoint contract."""
from fastapi.testclient import TestClient

from repopulse.main import app


def test_healthz_returns_ok() -> None:
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "RepoPulse"
    assert "version" in body


def test_healthz_includes_environment() -> None:
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.json()["environment"] == "development"
```

- [ ] **Step 2: Run test — expect failure (ModuleNotFoundError on `repopulse.main`)**

```bash
cd backend
.venv/Scripts/python -m pytest tests/test_health.py -v
```

- [ ] **Step 3: Create `backend/src/repopulse/__init__.py`**

```python
"""RepoPulse AIOps backend."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Write `backend/src/repopulse/api/health.py`**

```python
"""Health endpoint."""
from typing import Literal, TypedDict

from fastapi import APIRouter

from repopulse import __version__
from repopulse.config import Settings

router = APIRouter()


class HealthPayload(TypedDict):
    status: Literal["ok"]
    service: str
    environment: str
    version: str


@router.get("/healthz")
def healthz() -> HealthPayload:
    """Liveness probe — always returns ok if the app is up."""
    settings = Settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": __version__,
    }
```

- [ ] **Step 5: Write `backend/src/repopulse/main.py`**

```python
"""FastAPI application entry point."""
from fastapi import FastAPI

from repopulse import __version__
from repopulse.api.health import router as health_router

app = FastAPI(
    title="RepoPulse AIOps",
    version=__version__,
)
app.include_router(health_router)
```

- [ ] **Step 6: Run test — expect pass**

```bash
.venv/Scripts/python -m pytest tests/test_health.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Run full quality gate**

```bash
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m mypy
.venv/Scripts/python -m pytest
```

Expected: all exit 0; pytest reports 6 passed total (4 config + 2 health).

- [ ] **Step 8: Smoke-test the live server**

Start the server in the background, hit the endpoint, verify the JSON, then stop it:

```bash
.venv/Scripts/python -m uvicorn repopulse.main:app --port 8000 &
SERVER_PID=$!
sleep 2
curl -s http://localhost:8000/healthz
echo
kill $SERVER_PID 2>/dev/null
```

Expected response:
```json
{"status":"ok","service":"RepoPulse","environment":"development","version":"0.1.0"}
```

- [ ] **Step 9: Commit**

```bash
git add backend/src/repopulse/__init__.py backend/src/repopulse/main.py backend/src/repopulse/api/health.py backend/tests/test_health.py
git commit -m "feat(backend): /healthz endpoint with FastAPI app wiring (TDD)"
```

---

## Task 7 — CI Workflow (Backend Only)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  backend:
    name: backend (python)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      - name: Lint (ruff)
        run: ruff check src tests
      - name: Typecheck (mypy)
        run: mypy
      - name: Test (pytest)
        run: pytest -v
```

- [ ] **Step 2: Validate YAML parses**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Expected: exits 0 (no SyntaxError).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: backend lint/typecheck/test workflow"
```

---

## Task 8 — README Polish + Final Local Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace seed `README.md`** with the polished version:

````markdown
# RepoPulse AIOps

Production-grade AIOps reference project: observability, AI-assisted operations with guardrails, and measurable reliability outcomes. **Backend-first delivery** — the operator dashboard lands at the end, after the AIOps core and GitHub agentic workflows are shipped.

> Source plans live in [`plans/`](plans/). Active execution plan: [`plans/milestone-1-execution-plan.md`](plans/milestone-1-execution-plan.md). Higher-level roadmap: [`plans/aiops-detailed-implementation-plan.md`](plans/aiops-detailed-implementation-plan.md).

## Repository Layout

| Path | Purpose |
|---|---|
| [`backend/`](backend/) | FastAPI service + AIOps core (Python ≥3.11) |
| [`infra/`](infra/) | Local Docker Compose + OTel collector (M2+) |
| [`docs/`](docs/) | Architecture, SLO spec, security model, runbooks |
| [`adr/`](adr/) | Architecture Decision Records |
| [`.github/workflows/`](.github/workflows/) | Deterministic CI |

The dashboard (`frontend/`) lands in the final UI milestone, using the parked `dashboard` design skill at [`.claude/skills/design-system/SKILL.md`](.claude/skills/design-system/SKILL.md).

## Backend Bring-up

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn repopulse.main:app --reload --port 8000
```

`curl http://localhost:8000/healthz` → `{"status":"ok",...}`

## Quality Gates

| Stack | Lint | Typecheck | Test |
|---|---|---|---|
| backend | `ruff check src tests` | `mypy` | `pytest` |

CI runs all of the above on every push and PR (`.github/workflows/ci.yml`).

## Status

| Milestone | Scope | Status |
|---|---|---|
| M1 | Backend foundation | In progress |
| M2 | Observability + SLO baseline | Planned |
| M3 | AIOps core (detection / correlation / recommendations) | Planned |
| M5 | GitHub agentic workflows | Planned |
| M4 | Operator UI (dashboard) | Planned (last) |
| M6 | Portfolio polish | Planned (last) |

See [`docs/roadmap.md`](docs/roadmap.md) for milestone goals and acceptance criteria.

## Toolchain Preflight

Verified at [`docs/preflight-checklist.md`](docs/preflight-checklist.md). Required for milestone execution: Superpowers (workflow), Playwright CLI (parked for the UI milestone), Obsidian Skills (knowledge tooling), `typeui.sh` `dashboard` slug (parked for the UI milestone).
````

- [ ] **Step 2: Run the full quality gate locally end-to-end** (the verification gate from the parent plan §4):

```bash
cd backend
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m mypy
.venv/Scripts/python -m pytest -v
cd ..
```

Capture exit codes for each command. **Stop and report** if any non-zero.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: polish README with bring-up + quality gates + status table"
```

---

## Task 9 — Milestone 1 Handoff Report

**Files:**
- Create: `docs/superpowers/plans/milestone-1-handoff.md`

- [ ] **Step 1: Write the handoff doc** with the 5 sections required by the parent plan §"Review Loop":

1. **Files changed and why** — every file with one-line rationale.
2. **Commands run and outcomes** — the verification commands from Task 8 with exit codes.
3. **Test results and known gaps** — pytest count, anything skipped.
4. **Risk notes** — security (no secrets in repo, env-prefixed config), reliability (placeholder route only, no external calls), maintainability (single backend toolchain in M1; frontend toolchain follows in UI milestone).
5. **Proposed next-milestone prompt** — a one-paragraph brief for Milestone 2 (Observability + SLO baseline).

Include an **Evidence Log** subsection per the parent plan §"Anti-Hallucination Protocol → Evidence-First Rule":

```markdown
## Evidence Log
| Claim | Evidence Source | Verification Method |
|---|---|---|
| Backend tests pass | `backend/.venv/Scripts/python -m pytest` exit 0 | Re-run `pytest -v` |
| Lint clean | `ruff check src tests` exit 0 | Re-run that command |
| Typecheck clean | `mypy` exit 0 | Re-run that command |
| CI YAML valid | `python -c "import yaml; yaml.safe_load(...)"` exit 0 | Re-run that check |
| Health endpoint live | `curl http://localhost:8000/healthz` returned `{"status":"ok",...}` | Boot uvicorn + curl |
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/milestone-1-handoff.md
git commit -m "docs: Milestone 1 handoff report with evidence log"
```

- [ ] **Step 3: Print git log summary + tag**

```bash
git log --oneline
git tag -a v0.1.0-m1 -m "Milestone 1: Backend Foundation"
```

Expected: 8 commits (one per task plus the README polish commit).

---

## Self-Review Pass

**Spec coverage** (Milestone 1 acceptance criteria from parent plan, **adjusted** for backend-first variant):
- ✅ "preflight-checklist.md exists and verifies required installs/workflow readiness" → Task 3
- ✅ "backend starts locally" → Task 6 (uvicorn smoke). **Frontend bring-up deferred** to UI milestone (variance from parent plan, documented in Scope Note).
- ✅ "CI pipeline is reproducible and deterministic" → Task 7 (pinned `actions/setup-python@v5`)
- ✅ "Docs cover architecture, roadmap, and security assumptions" → Task 2

**Build items from parent plan §Milestone 1 (backend-relevant only)**:
- ✅ Mandatory preflight completion → Task 3
- ✅ Backend FastAPI app + health + settings → Tasks 4-6
- ⏭ Frontend Next.js / Tailwind / shadcn baseline — **deferred** to UI milestone per scope decision
- ✅ CI lint/type/test (backend) → Task 7
- ✅ Base docs + ADR-001 → Task 2
- ✅ `docs/ui-design-system.md` initialized with selected slug → Task 2

**Type/name consistency check:**
- `Settings` class used in both `tests/test_config.py` (Task 5) and `api/health.py` (Task 6). ✅
- `__version__` defined in `__init__.py` (Task 6) and used in `health.py` and `main.py`. ✅
- `app_name` field in `Settings` returned as `service` in the health payload (intentional rename — health response surfaces a friendlier key for downstream observability). Documented in this self-review note. ✅
- `REPOPULSE_` env prefix consistent across `config.py` and `tests/test_config.py`. ✅

**Placeholder scan:** No "TBD" / "TODO" / "implement later" in implementation tasks. The two intentional `STATUS: STUB`-style markers (`docs/slo-spec.md` and `docs/ui-design-system.md` "deferred component primitives" note) are deliberate per the parent plan and explicitly labeled.

**TDD compliance:** Tasks 5 and 6 follow RED-GREEN-REFACTOR strictly: failing test first (`pytest` invocation captured before any production code is written), expected failure documented, minimal code to pass, commit. Tasks 1-4 and 7-9 are scaffolding/docs/CI — no production logic, no TDD required (per superpowers:test-driven-development "Exceptions" list: configuration files).

**UI Hold Gate respected:** No frontend code in this milestone. The `dashboard` SKILL.md is parked at `.claude/skills/design-system/SKILL.md` and only referenced by docs.

**Windows compatibility:** All commands use bash-compatible syntax (`.venv/Scripts/python` works on Windows; `find` works in git-bash). CI runs on `ubuntu-latest`. No npm/npx commands in the M1 task set — Node tooling is not exercised in M1.

---

## Execution Handoff

Plan complete and saved to `plans/milestone-1-execution-plan.md`. Two execution options:

**1. Subagent-Driven** — Dispatch a fresh subagent per task, two-stage review (spec compliance → code quality), fast iteration. Higher token cost; safer for autonomous runs.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch with checkpoints between tasks. Lower token cost; you see each step.

Recommendation: **Inline with checkpoints after Task 6 (backend app done) and Task 7 (CI in)** — most M1 tasks have sequential dependencies (venv → install → tests), so subagent parallelism doesn't buy much.
