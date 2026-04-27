# Contributing

## Workflow

1. **Branch** from `main` (`git checkout -b feat/<topic>`).
2. **TDD** — write a failing test before the code that makes it pass. Every
   commit that adds behavior should pair a test commit with the
   implementation. The `(TDD)` suffix on commit messages is the project
   convention.
3. **Lint + typecheck + test** before pushing:
   - Backend: `pytest && ruff check src tests && mypy`
   - Frontend: `npm test && npm run typecheck && npm run lint && npm run build`
4. **PR** — fill the template (summary + test plan).

## Commit messages

We follow [Conventional Commits](https://www.conventionalcommits.org/) loosely:

- `feat(scope): subject` for new behavior
- `fix(scope): subject` for bug fixes
- `docs(scope): subject` for docs only
- `chore(scope): subject` for tooling
- `test(scope): subject` for tests-only commits
- `plan: subject` for planning artifacts

`scope` is one of: `backend`, `api`, `pipeline`, `frontend`, `bench`,
`m1..m6`, `demo`, `github`, etc.

## Code review

We dispatch the `superpowers:code-reviewer` subagent before each milestone
tag. Review reports live under
`docs/superpowers/plans/m<n>-evidence/code-review.md`. The receiving end
follows `superpowers:receiving-code-review` discipline:

1. **Verify** each finding against the codebase before fixing — the
   reviewer can be wrong.
2. **Push back** with technical reasoning when the reviewer is wrong.
3. **Fix Criticals + Importants**, defer minors with reasoning.
4. **Add a regression test** for every fix.

## Definition of done

A change is done when:
- All tests pass.
- Lint + typecheck + build green.
- New behavior has a test (TDD).
- If user-facing: a screenshot lives under
  `docs/superpowers/plans/m<n>-evidence/screenshots/`.
- A claim made in a handoff or report has a re-runnable command + captured
  artifact.

## Anti-hallucination rule

We do not claim something works without evidence. Every metric in
[results-report.md](results-report.md) cites the JSON path it came from.
Every "tests pass" claim has the count + the command. Every milestone
handoff has an Evidence Log mapping every claim to a re-runnable
command.

## Skills used

This project uses [Superpowers](https://github.com/anthropic-experimental/claude-code-superpowers)
skills extensively. Key ones:

- `superpowers:writing-plans` — every milestone starts with a plan.
- `superpowers:test-driven-development` — every behavior change.
- `superpowers:systematic-debugging` — every non-trivial failure.
- `superpowers:verification-before-completion` — before any "done" claim.
- `superpowers:requesting-code-review` + `:receiving-code-review` — every
  milestone tag.

If you're not using Claude Code with the Superpowers plugin, you can still
follow the same discipline by hand — the plans + handoffs document what
to do.
