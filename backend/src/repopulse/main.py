"""FastAPI application entry point.

Exposes a ``create_app`` factory so tests can inject in-memory exporters.
The module-level ``app`` is the production instance and uses the default
console exporter from :func:`repopulse.telemetry.init_telemetry`.

Note on instrumentation order: ``FastAPIInstrumentor.instrument_app``
patches ``app.build_middleware_stack``. Starlette caches the result of
``build_middleware_stack`` on the first ``__call__`` (which is the lifespan
startup). If we instrumented inside the lifespan, the patch would land
*after* the middleware stack had already been cached — and the OTel
middleware would never run. We therefore instrument eagerly inside
``create_app`` (before the app handles any request) and use the lifespan
solely for graceful shutdown.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.trace.export import SpanExporter

from repopulse import __version__
from repopulse.api.actions import router as actions_router
from repopulse.api.events import router as events_router
from repopulse.api.github_workflows import router as github_workflows_router
from repopulse.api.health import router as health_router
from repopulse.api.incidents import router as incidents_router
from repopulse.api.recommendations import router as recommendations_router
from repopulse.api.slo import router as slo_router
from repopulse.config import Settings
from repopulse.pipeline.orchestrator import PipelineOrchestrator
from repopulse.telemetry import init_telemetry


def create_app(
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
    orchestrator: PipelineOrchestrator | None = None,
) -> FastAPI:
    """Build a FastAPI app with telemetry + AIOps pipeline wired in eagerly.

    Tests pass ``InMemorySpanExporter`` / ``InMemoryMetricReader`` and may
    inject a pre-populated ``PipelineOrchestrator``; production callers
    leave the kwargs ``None`` to get console exporters and a fresh
    orchestrator. Active providers + orchestrator are stored on
    ``app.state`` so handlers and tests can reach them via the request.
    """
    settings = Settings()
    tracer_provider, meter_provider = init_telemetry(
        settings,
        span_exporter=span_exporter,
        metric_reader=metric_reader,
    )
    if orchestrator is None:
        orchestrator = PipelineOrchestrator()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            FastAPIInstrumentor.uninstrument_app(_app)
            tracer_provider.force_flush()
            tracer_provider.shutdown()
            meter_provider.shutdown()

    fastapi_app = FastAPI(
        title="RepoPulse AIOps",
        version=__version__,
        lifespan=lifespan,
    )
    FastAPIInstrumentor.instrument_app(
        fastapi_app,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
    fastapi_app.state.tracer_provider = tracer_provider
    fastapi_app.state.meter_provider = meter_provider
    fastapi_app.state.orchestrator = orchestrator
    fastapi_app.state.settings = settings
    fastapi_app.include_router(health_router)
    fastapi_app.include_router(events_router)
    fastapi_app.include_router(recommendations_router)
    fastapi_app.include_router(incidents_router)
    fastapi_app.include_router(actions_router)
    fastapi_app.include_router(slo_router)
    fastapi_app.include_router(github_workflows_router)
    return fastapi_app


app = create_app()
