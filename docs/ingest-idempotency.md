# Ingest idempotency contract

`POST /api/v1/events` is idempotent on `event_id`. The full contract,
shipped in M2.0 T6 (v2.0.0-storage):

## Response shape

| Outcome                              | Status | Body                                                                  |
| ------------------------------------ | -----: | --------------------------------------------------------------------- |
| Fresh `event_id` accepted            |  `202` | `{"accepted": true, "event_id": "<uuid>", "duplicate": false}`        |
| `event_id` already ingested          |  `202` | `{"accepted": true, "event_id": "<uuid>", "duplicate": true}`         |
| Validation error (bad UUID, etc.)    |  `422` | FastAPI standard error envelope                                       |
| Auth missing / wrong                 |  `401` | `{"detail": "..."}`                                                   |
| API secret unconfigured              |  `503` | `{"detail": "..."}`                                                   |
| Body over `REPOPULSE_MAX_REQUEST_BYTES` | `413` | `{"detail": "..."}`                                                   |
| `simulate_error=true` and gated      |  `403` | `{"detail": "..."}`                                                   |
| `simulate_error=true` and allowed    |  `500` | (unhandled; intentional)                                              |

## Why 202 on duplicates and not 409

The whole point of an `event_id` is to make retries safe. Network blips,
load-balancer resets, sidecar buffering, and at-least-once message-bus
semantics all produce duplicate POSTs as a normal operating mode — not as
client errors. Returning `409 Conflict` would force every well-behaved
client to special-case a benign retry, treating "this already worked"
the same way they treat "your request is malformed."

`202 + duplicate: true` says: **the server's state matches what you wanted,
and you didn't cause any extra work doing it.** A client that wants to
detect retries can read the `duplicate` flag; a client that doesn't can
ignore it and treat both responses the same way.

`409` is reserved for the **state-machine-violation** case (post-T6 only):
attempting to approve or reject a recommendation whose state is not
`pending` returns `409` because that operation is intentionally
single-shot.

## How idempotency is enforced

The `raw_events` table's primary key is `event_id`. The repository's
`insert_raw_idempotent` issues:

```sql
INSERT INTO raw_events (event_id, source, kind, payload, received_at, occurred_at)
VALUES (...)
ON CONFLICT (event_id) DO NOTHING
RETURNING event_id
```

If `RETURNING` yields a row, the insert was new → the orchestrator runs
normalize + (optionally) evaluate. If `RETURNING` yields nothing, the
event was a duplicate → the orchestrator skips the rest and the route
sets `duplicate: true`.

This is the **per-event side** of v1.1's in-memory `_seen_keys` LRU,
lifted into the database. The **content side** of dedup
(`incidents.signature_hash` UNIQUE) handles the equivalent for incidents
during `evaluate()` — see
[milestone-2.0-storage-plan.md](./superpowers/plans/milestone-2.0-storage-plan.md)
§3.3.

## Client implementation guidance

```python
import requests
from uuid import uuid4

def ingest_with_retry(envelope: dict, *, max_attempts: int = 3) -> None:
    """POST an event with safe retries.

    The same envelope (same event_id) can be POSTed any number of times
    without producing duplicate persistence side-effects. Pass max_attempts
    high enough to ride out transient network errors.
    """
    envelope = {**envelope, "event_id": envelope.get("event_id") or str(uuid4())}
    for attempt in range(max_attempts):
        try:
            r = requests.post(URL, json=envelope, headers=AUTH, timeout=10)
            r.raise_for_status()
            body = r.json()
            if body.get("duplicate"):
                # Already ingested on a prior attempt; nothing to do.
                return
            # Fresh insert succeeded.
            return
        except requests.RequestException:
            if attempt == max_attempts - 1:
                raise
            time.sleep(2 ** attempt)
```

The `event_id` is the contract: keep it stable across retries, and the
ingest endpoint will keep the database state coherent.
