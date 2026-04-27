# Troubleshooting

## Backend won't start

- `from repopulse import __version__` should work after `pip install -e .[dev]`.
  If it doesn't: re-run from inside the venv, or recreate the venv.
- Port already in use: `netstat -ano | findstr :8000` (Windows) or
  `lsof -i :8000` (Unix); kill the process or pick another port.

## Frontend `npm test` fails with "@base-ui/react" missing

The toast component (M5) needs `@base-ui/react`. If your `node_modules`
predates that addition, run `npm install` again from `frontend/`.

## Docker collector not starting

`docker compose up -d otel-collector` fails with "no permission" on Linux:
- Add yourself to the `docker` group: `sudo usermod -aG docker $USER`,
  then log out and back in.
- On WSL Ubuntu, ensure Docker Desktop's WSL integration is enabled
  (Settings → Resources → WSL Integration).

## Tests pass locally but build fails on CI

Most likely Node version mismatch — Next.js 15 needs Node 20+. Check
`.github/workflows/ci.yml` for the version pin and your local
`node --version`.

## Magic MCP / 21st-dev tools don't appear in Claude Code

The `magic` MCP server only loads at session start. After running
`claude mcp add ...`, restart Claude Code in this directory to see the
`21st_magic_*` tools.

## `./scripts/demo.sh` says "backend venv not found"

Run the backend setup first:

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate          # Windows cmd: .venv\Scripts\activate
pip install -e ".[dev]"
```

Then re-run `./scripts/demo.sh` from the repo root.

## Benchmark reports false_positive_rate > 0

If you see false positives after running the benchmark on a clean
checkout: this is a regression — please open an issue. The v1.0.0
benchmark.json (committed in `docs/superpowers/plans/m6-evidence/`) shows
**0% false positives**. The regression test
`test_run_scenario_loaded_fixture_with_anomalies_does_not_observe`
guards against the historical bug where anomaly timestamps weren't
re-anchored to runtime `now`.

## Mypy "Source file found twice under different module names"

Your venv is shadowing the workspace install. Recreate:

```bash
cd backend
deactivate || true
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
mypy
```

## Dashboard is blank on `localhost:3000`

Check that the backend is reachable:

```bash
curl http://127.0.0.1:8000/healthz
```

If 200 OK: ensure the frontend was started with the right backend URL:

```bash
NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000 npm run start -- -p 3000
```

If the URL was wrong at start, restart `npm run start` — Next reads it
once at boot.
