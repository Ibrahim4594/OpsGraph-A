"""OpenTelemetry initialization for the RepoPulse backend.

`init_telemetry` builds and returns a `TracerProvider` and a `MeterProvider`
configured with a service-identifying `Resource`. Globals are intentionally
NOT modified — callers (for example the FastAPI lifespan) are responsible
for `trace.set_tracer_provider(...)` if they want auto-instrumentation to
pick up these providers. Keeping the function side-effect-free makes it
trivially testable with in-memory exporters.
"""
from __future__ import annotations

import os

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    InMemoryMetricReader,
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)

from repopulse import __version__
from repopulse.config import Settings

SERVICE_NAME = "repopulse-backend"


def _build_resource(settings: Settings) -> Resource:
    return Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": __version__,
            "deployment.environment": settings.environment,
        }
    )


def init_telemetry(
    settings: Settings,
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> tuple[TracerProvider, MeterProvider]:
    """Build and return ``(TracerProvider, MeterProvider)`` for the backend.

    - ``span_exporter`` defaults to ``ConsoleSpanExporter`` so the local-dev
      experience prints spans to stdout without extra setup. Tests should
      pass an ``InMemorySpanExporter``.
    - ``metric_reader`` defaults to a ``PeriodicExportingMetricReader`` over
      the console metric exporter (60 s interval). When
      ``REPOPULSE_UNDER_PYTEST=1`` (set by ``tests/conftest.py`` before
      collection imports app code), defaults to ``InMemoryMetricReader`` so
      no background export thread writes to a closed stdout after the suite.
      Tests may still pass an explicit ``InMemoryMetricReader``.
    - All exporters use ``SimpleSpanProcessor`` (synchronous export).
      This is intentional for the AIOps service's expected throughput and
      avoids background-thread teardown races (notably the
      ``BatchSpanProcessor`` writing to a closed stdout during pytest
      shutdown). Switch to ``BatchSpanProcessor`` if/when M3+ load demands.
    """
    resource = _build_resource(settings)

    if span_exporter is None:
        span_exporter = ConsoleSpanExporter()

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))

    if metric_reader is None:
        if os.environ.get("REPOPULSE_UNDER_PYTEST") == "1":
            metric_reader = InMemoryMetricReader()
        else:
            metric_reader = PeriodicExportingMetricReader(
                ConsoleMetricExporter(),
                export_interval_millis=60_000,
            )

    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])

    return tracer_provider, meter_provider
