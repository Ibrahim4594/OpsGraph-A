# Preflight Checklist

This document verifies that the mandatory tools from [`../plans/aiops-detailed-implementation-plan.md`](../plans/aiops-detailed-implementation-plan.md) § "Mandatory Agent Skill and Toolchain Preflight" are installed and callable. Evidence captured during the install session on 2026-04-26 / 2026-04-27.

## 1. Superpowers (`obra/superpowers`)

- **Source:** https://github.com/obra/superpowers
- **Install method:** Claude Code plugin marketplace `claude-plugins-official`. Plugin restored from clean state via `git clone --depth 1 --branch v5.0.7 https://github.com/obra/superpowers.git` into `C:\Users\ibrah\.claude\plugins\cache\claude-plugins-official\superpowers\5.0.7\`.
- **Version:** v5.0.7
- **Commit SHA:** `1f20bef3f59b85ad7b52718f822e37c4478a3ff5` (matches the dereferenced `refs/tags/v5.0.7`)
- **Manifest verified:** `plugin.json` parses; `name: superpowers`, `version: 5.0.7`.
- **Skills present (14):** brainstorming, dispatching-parallel-agents, executing-plans, finishing-a-development-branch, receiving-code-review, requesting-code-review, subagent-driven-development, systematic-debugging, test-driven-development, using-git-worktrees, using-superpowers, verification-before-completion, writing-plans, writing-skills.
- **Use in M1:** `superpowers:writing-plans` (this plan), `superpowers:test-driven-development` (Tasks 5–6), `superpowers:executing-plans` (this loop), `superpowers:verification-before-completion` (Task 8).

## 2. Playwright CLI (`@playwright/cli`)

- **Source:** https://www.npmjs.com/package/@playwright/cli (the original docs at https://github.com/microsoft/playwright-cli redirect/relocate to `@playwright/cli`).
- **Install method:** `npm install -g @playwright/cli@latest` then `playwright-cli install --skills` from the project root.
- **Version:** `0.1.9`
- **Binary path:** `C:\Users\ibrah\AppData\Roaming\npm\playwright-cli`
- **Project skills:** [`.claude/skills/playwright-cli/SKILL.md`](../.claude/skills/playwright-cli/SKILL.md) + `references/`.
- **Default browser detected:** Chrome.
- **Verification:** `playwright-cli --help` exits 0 and prints the documented command list (`open`, `goto`, `snapshot`, `click`, `screenshot`, …).
- **Reserved for:** browser-driven verification in the deferred UI milestone. Not exercised in M1.

## 3. Obsidian Skills (`kepano/obsidian-skills`)

- **Source:** https://github.com/kepano/obsidian-skills
- **Install method:** `npx -y skills add https://github.com/kepano/obsidian-skills.git -g -y --all` (CLI: `vercel-labs/skills` — npm package `skills@1.5.1`).
- **Skills installed:** `obsidian-markdown`, `obsidian-bases`, `json-canvas`, `obsidian-cli`, `defuddle` (5 skills).
- **Source path:** `C:\Users\ibrah\.agents\skills\<skill>` (symlinked into `C:\Users\ibrah\.claude\skills\`).
- **Risk assessments (from CLI output):** `obsidian-markdown=Safe`; `obsidian-bases=Low`; `json-canvas=Low`; `obsidian-cli=Med (Gen)`; `defuddle=Med (Snyk)`. Med-risk skills only activate when explicitly invoked.

## 4. Awesome Design Skills (`bergside/awesome-design-skills` → `typeui.sh`)

- **Status:** CLI cached + `dashboard` slug pulled.
- **Source:** https://github.com/bergside/awesome-design-skills (npm package: `typeui.sh@0.7.0`).
- **Install method:** `npx -y typeui.sh` — package cached at `C:\Users\ibrah\AppData\Local\npm-cache\_npx\1d023e8bfdadd56a\node_modules\typeui.sh\`.
- **Verification:** `node <cache>/typeui.sh/dist/cli.js --help` exits 0 and lists commands `generate`, `update`, `pull <slug>`, `list`, `randomize`.
- **Skill pulled:** `dashboard` (2026-04-27) via `npx typeui.sh pull dashboard -p claude-code -f skill` →
  - [`.claude/skills/design-system/SKILL.md`](../.claude/skills/design-system/SKILL.md)
  - [`.agents/skills/design-system/SKILL.md`](../.agents/skills/design-system/SKILL.md)
  - Both 4.2 KB, identical content, frontmatter `name: dashboard`.
- **Provider naming gotcha:** the public docs show `-p claude` but the CLI rejects that with `Unsupported providers: claude. Supported: …claude-code…`. Use `claude-code`.
- **UI Hold Gate:** still in force. The skill is loaded so guidelines are ready for the deferred UI milestone.

## Phase 0 Compliance

The parent plan's Phase 0 strict order is satisfied:

1. ✅ Install skills/tools from official sources.
2. ✅ Invoke/verify skills/tools (commands above produce documented output).
3. ✅ Read implementation plan ([`../plans/aiops-detailed-implementation-plan.md`](../plans/aiops-detailed-implementation-plan.md)).
4. ⏭ Begin Milestone 1 work — the active execution plan ([`../plans/milestone-1-execution-plan.md`](../plans/milestone-1-execution-plan.md)) is now in flight.

## Windows-Specific Notes

- The user's PowerShell has script execution disabled, so `npx.ps1` fails. Use `cmd.exe /c npx ...` or run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` for direct PowerShell use. Bash (git-bash) and `node`-direct invocations work without changes.
- Git's `core.autocrlf` is the Windows default — committed files are stored LF in the index but check out CRLF on disk. The `.editorconfig` enforces LF for new content; this is consistent with CI on `ubuntu-latest`.
- Docs target: any machine running Python ≥3.11. Local dev tested on Windows 11 Pro 10.0.26200 with Python 3.14.3 and Node v24.14.1 (Node retained for tooling — frontend stack lands in the deferred UI milestone).
