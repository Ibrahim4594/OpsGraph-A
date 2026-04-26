"""Synthetic load generator for ``POST /api/v1/events``.

The :func:`generate_load` function is pure — it takes a ``post`` callable
that maps ``(url, envelope) -> http_status_code`` and returns a counted
:class:`LoadResult`. The CLI wrapper at the bottom of this module
constructs an :mod:`httpx` client and supplies a real ``post`` callable;
unit tests inject a fake.

Determinism: the *first* ``ceil(requests * error_rate)`` requests in the
sequence are flagged ``simulate_error=True``, so a given
``(requests, error_rate)`` always produces exactly the same error count.
This makes burn-rate evidence reproducible.
"""
from __future__ import annotations

import argparse
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import uuid4

PostFn = Callable[[str, dict[str, object]], int]


@dataclass
class LoadResult:
    total: int
    success_count: int
    error_count: int
    latencies_ms: list[float] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"LoadResult(total={self.total}, success={self.success_count}, "
            f"errors={self.error_count}, p50_ms={self._percentile(50):.2f}, "
            f"p95_ms={self._percentile(95):.2f})"
        )

    def _percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        ordered = sorted(self.latencies_ms)
        k = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * p / 100) - 1))
        return ordered[k]


def generate_load(
    *,
    requests: int,
    error_rate: float,
    target_url: str,
    post: PostFn,
) -> LoadResult:
    """Drive ``requests`` POSTs against ``target_url`` and tally the results."""
    if not 0.0 <= error_rate <= 1.0:
        raise ValueError(f"error_rate must be in [0, 1]; got {error_rate!r}")
    if requests < 0:
        raise ValueError("requests must be non-negative")

    error_quota = math.ceil(requests * error_rate)
    success_count = 0
    error_count = 0
    latencies: list[float] = []

    for i in range(requests):
        envelope: dict[str, object] = {
            "event_id": str(uuid4()),
            "source": "synthetic",
            "kind": "load-test",
            "payload": {"index": i},
        }
        if i < error_quota:
            envelope["simulate_error"] = True

        start = time.perf_counter()
        status = post(target_url, envelope)
        latencies.append((time.perf_counter() - start) * 1000.0)

        if 200 <= status < 300:
            success_count += 1
        else:
            error_count += 1

    return LoadResult(
        total=requests,
        success_count=success_count,
        error_count=error_count,
        latencies_ms=latencies,
    )


def _real_post(url: str, envelope: dict[str, object]) -> int:
    import httpx  # local import keeps unit tests free of network deps

    with httpx.Client(timeout=5.0) as client:
        response = client.post(url, json=envelope)
        return response.status_code


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Drive synthetic load at the RepoPulse /api/v1/events ingest endpoint.",
    )
    parser.add_argument("--requests", type=int, required=True)
    parser.add_argument("--error-rate", type=float, default=0.0)
    parser.add_argument(
        "--target",
        default="http://127.0.0.1:8000/api/v1/events",
        help="Target URL for POST",
    )
    args = parser.parse_args()
    result = generate_load(
        requests=args.requests,
        error_rate=args.error_rate,
        target_url=args.target,
        post=_real_post,
    )
    print(result.summary())


if __name__ == "__main__":  # pragma: no cover
    main()
