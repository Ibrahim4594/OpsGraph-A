# SLO Specification

> **STATUS: Active (M2).** This file replaces the M1 stub. SLI/SLO definitions, formulas, and burn-rate alerts are now sourced directly from the Python implementation in [`backend/src/repopulse/slo.py`](../backend/src/repopulse/slo.py) so the spec and the code cannot drift.

## Service Catalog

| Service | Component | Owner |
|---|---|---|
| `repopulse-backend` | FastAPI ingest API + AIOps core (M3+) | Backend (single owner today) |

Future services (event bus consumers, recommendation workers) will be added as they are introduced in later milestones with their own SLO rows.

## SLIs and SLOs (`repopulse-backend`)

| ID | SLI | Numerator / Denominator | Window | Target | Source function |
|---|---|---|---|---|---|
| `S1` | **Request availability** | `success_count / total_count` over events from `/api/v1/events` (counts of HTTP responses; 2xx/3xx = success, 5xx = failure; 4xx is excluded as caller error) | 30 d rolling | **99.9 %** | [`availability_sli`](../backend/src/repopulse/slo.py) |
| `S2` | **Request latency p95** | Fraction of `/api/v1/events` requests with server-measured duration ≤ 250 ms | 30 d rolling | **99 %** of requests under 250 ms | [`latency_sli`](../backend/src/repopulse/slo.py) |
| `S3` | **Health probe availability** | `success_count / total_count` for `/healthz` (effectively a process-up SLI) | 30 d rolling | **99.95 %** | [`availability_sli`](../backend/src/repopulse/slo.py) |

The `total_count` and `success_count` for `S1`/`S3` come from the `http.server.duration` metric and `http.server.response.status_code` attribute emitted by `opentelemetry-instrumentation-fastapi`. Latency samples for `S2` come from the same histogram's bucket boundaries (or raw spans during M2 evidence runs).

## Error Budget

For each SLO with target `T`, the allowed error fraction is `1 − T`:

| SLO | Target | Error budget |
|---|---|---|
| `S1` | 0.999 | 0.001 (≈ 43.2 minutes / 30 d) |
| `S2` | 0.99 latency-meeting fraction | 0.01 (≈ 7.2 hours / 30 d) |
| `S3` | 0.9995 | 0.0005 (≈ 21.6 minutes / 30 d) |

Computed by [`error_budget(slo)`](../backend/src/repopulse/slo.py) so the spec and code stay in lockstep.

## Burn-Rate Alerting

Following the Google SRE Workbook (chapter 5, "Alerting on SLOs") **multi-window** strategy. For each SLO the **burn rate** is the ratio of the actual error rate over a window to the budgeted error rate:

```
burn = actual_error_rate / (1 − target)
```

Implemented by [`burn_rate(...)`](../backend/src/repopulse/slo.py).

| Alert | Window | Threshold | Action |
|---|---|---|---|
| **Fast burn** | 1 hour | `burn ≥ 14.4` (consumes ≥ 2 % of monthly budget per hour) | **Page** the on-call engineer |
| **Slow burn** | 6 hours | `burn ≥ 6.0` (consumes ≥ 5 % of monthly budget over the window) | **Open a ticket** for triage within the business day |

Implemented by [`is_fast_burn`](../backend/src/repopulse/slo.py) and [`is_slow_burn`](../backend/src/repopulse/slo.py). Default thresholds are the Google SRE workbook recommended values; the functions accept a `threshold=` override for service-specific tuning later.

## Worked Example

For `S1` (`target = 0.999`, `error_budget = 0.001`):

- A 1 h window with 1 000 requests, 14 errors → `actual_error_rate = 0.014`, `burn = 0.014 / 0.001 = 14.0`. **Slow burn** (`6 ≤ 14 < 14.4`), ticket.
- A 1 h window with 1 000 requests, 15 errors → `burn = 15.0`. **Fast burn** (`≥ 14.4`), page.
- A 6 h window with 10 000 requests, 60 errors → `actual = 0.006`, `burn = 6.0`. **Slow burn**, ticket.

Compute these yourself with:

```python
from repopulse.slo import SLO, availability_sli, burn_rate, is_fast_burn, is_slow_burn

slo = SLO(target=0.999)
sli = availability_sli(success_count=985, total_count=1000)         # 0.985
err = 1 - sli                                                        # 0.015
burn = burn_rate(actual_error_rate=err, slo=slo)                     # 15.0
is_fast_burn(burn=burn)                                              # True
```

## Open Items (deferred to M3+)

- Per-route SLO breakdown (currently aggregated at the service level).
- Promote burn-rate computation from manual scripting to a periodic background task that exposes `aiops_burn_rate{slo}` as a metric.
- Wire alerts into Alertmanager / PagerDuty-equivalent (M5 GitHub agentic workflows can post to issues until then).

## Stability Contract

The functions in [`backend/src/repopulse/slo.py`](../backend/src/repopulse/slo.py) form the stable surface; their signatures are covered by tests in [`backend/tests/test_slo.py`](../backend/tests/test_slo.py). When this spec changes, those tests change first (TDD).
