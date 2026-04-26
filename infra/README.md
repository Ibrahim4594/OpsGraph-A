# Infra

Local infrastructure for RepoPulse — currently a single OpenTelemetry Collector container that receives OTLP from the backend and exports to stdout + JSONL files for inspection.

## Bring-up (optional — for full OTLP path validation)

```bash
cd infra
mkdir -p output
docker compose up -d
docker compose ps         # collector should be "running"
docker compose logs -f    # tail console exporter output
```

The collector listens on:

| Port | Protocol | Purpose |
|---|---|---|
| 4317 | gRPC | OTLP receiver |
| 4318 | HTTP | OTLP receiver |
| 13133 | HTTP | reserved for `health_check` extension (added in a later milestone) |

Output files are written to `infra/output/` (gitignored via the root `.gitignore`):

- `spans.jsonl`
- `metrics.jsonl`
- `logs.jsonl`

## Config

The collector config is `otel-collector-config.yaml`. Pipelines for traces, metrics, and logs each go through `memory_limiter → batch` and fan out to the `debug` (stdout) and `file/<signal>` exporters. Production exporters (Prometheus/Tempo/Loki, Grafana Cloud, Honeycomb, etc.) are added in later milestones.

## Local-only telemetry without Docker

The backend's default `init_telemetry` exporter is `ConsoleSpanExporter` + `ConsoleMetricExporter` to stdout. That path is exercised in [`docs/runbooks/telemetry-validation.md`](../docs/runbooks/telemetry-validation.md) and is the canonical source of M2 evidence (no Docker required).

Use the OTLP collector path when validating the wire protocol or testing exporter configurations.
