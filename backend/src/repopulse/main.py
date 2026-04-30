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

Storage wiring (T6):

- Production: lifespan startup builds an :class:`AsyncEngine` +
  :class:`async_sessionmaker` from :data:`Settings.database_url`, then
  constructs the async :class:`PipelineOrchestrator` over that
  sessionmaker. The engine is disposed on shutdown.
- Tests: pass ``orchestrator=...`` (built via
  :func:`repopulse.testing.make_inmem_orchestrator`) to skip the
  real engine path entirely.
- Misconfiguration: when no orchestrator is supplied AND
  ``REPOPULSE_DATABASE_URL`` is unset, ``create_app`` raises
  ``RuntimeError`` immediately — the app fails loudly rather than
  starting in a half-broken state where reads return empty and writes
  silently no-op.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.trace.export import SpanExporter
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request

from repopulse import __version__
from repopulse.api.actions import router as actions_router
from repopulse.api.events import router as events_router
from repopulse.api.github_workflows import router as github_workflows_router
from repopulse.api.health import router as health_router
from repopulse.api.incidents import router as incidents_router
from repopulse.api.recommendations import router as recommendations_router
from repopulse.api.slo import router as slo_router
from repopulse.config import Settings
from repopulse.db.engine import make_engine_from_settings, make_session_factory
from repopulse.pipeline.async_orchestrator import PipelineOrchestrator
from repopulse.telemetry import init_telemetry


def create_app(
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
    orchestrator: PipelineOrchestrator | None = None,
) -> FastAPI:
    """Build a FastAPI app with telemetry + AIOps pipeline wired in eagerly.

    Tests pass ``InMemorySpanExporter`` / ``InMemoryMetricReader`` and an
    ``orchestrator`` built via the in-memory test helper to skip the DB.
    Production callers leave ``orchestrator=None``; the lifespan startup
    constructs the real :class:`PipelineOrchestrator` from
    :data:`Settings.database_url`.

    Raises:
        RuntimeError: ``orchestrator is None`` AND
            ``Settings.database_url`` is unset. v2.0 has no in-memory
            production path — every read goes through the persistent
            store, so misconfiguration must be loud.
    """
    settings = Settings()
    tracer_provider, meter_provider = init_telemetry(
        settings,
        span_exporter=span_exporter,
        metric_reader=metric_reader,
    )

    engine: AsyncEngine | None = None
    if orchestrator is None:
        # Production path: refuse to start without a configured DB.
        if not settings.database_url:
            raise RuntimeError(
                "REPOPULSE_DATABASE_URL is unset and no orchestrator was "
                "injected. v2.0 requires the persistent storage layer; set "
                "REPOPULSE_DATABASE_URL or pass `orchestrator=` (tests use "
                "repopulse.testing.make_inmem_orchestrator)."
            )
        engine = make_engine_from_settings(settings)
        session_maker = make_session_factory(engine)
        orchestrator = PipelineOrchestrator(session_maker=session_maker)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            FastAPIInstrumentor.uninstrument_app(_app)
            tracer_provider.force_flush()
            tracer_provider.shutdown()
            meter_provider.shutdown()
            if engine is not None:
                await engine.dispose()

    fastapi_app = FastAPI(
        title="RepoPulse AIOps",
        version=__version__,
        lifespan=lifespan,
    )
    _max_bytes = settings.max_request_bytes

    class _BodySizeLimitMiddleware(BaseHTTPMiddleware):
        """Reject requests whose ``Content-Length`` exceeds ``max_request_bytes``.

        v1.1 post-review I1 fix. Runs before Starlette's body parser, so a
        malicious caller cannot OOM the worker by sending a multi-MB body
        even though the per-payload validator (256 KiB) would later reject it.
        """

        async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
            cl = request.headers.get("content-length")
            if cl is not None:
                try:
                    n = int(cl)
                except ValueError:
                    return JSONResponse(
                        {"detail": "invalid Content-Length"}, status_code=400
                    )
                if n > _max_bytes:
                    return JSONResponse(
                        {
                            "detail": (
                                f"request body too large: {n} bytes exceeds "
                                f"{_max_bytes} byte limit"
                            )
                        },
                        status_code=413,
                    )
            return await call_next(request)

    fastapi_app.add_middleware(_BodySizeLimitMiddleware)
    if settings.cors_origins.strip():
        _origins = [
            o.strip() for o in settings.cors_origins.split(",") if o.strip()
        ]
        # CORS hardening (v1.1 post-review C1): the dashboard sends an
        # Authorization bearer that the browser holds in a public env var
        # (NEXT_PUBLIC_API_SHARED_SECRET, see ADR-005). Letting any origin
        # send credentialed requests would defeat browser SOP — Starlette
        # reflects the requesting Origin back when "*" is used, so this is
        # not safe even though the spec ostensibly forbids it. Fail fast.
        if any(o == "*" for o in _origins):
            raise ValueError(
                "REPOPULSE_CORS_ORIGINS must not contain a wildcard ('*'); "
                "list explicit origins instead. See ADR-005 + docs/security-model.md."
            )
        if _origins:
            fastapi_app.add_middleware(
                CORSMiddleware,
                allow_origins=_origins,
                allow_credentials=True,
                allow_methods=["GET", "POST"],
                allow_headers=["Authorization", "Content-Type"],
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
    fastapi_app.state.engine = engine
    fastapi_app.include_router(health_router)
    fastapi_app.include_router(events_router)
    fastapi_app.include_router(recommendations_router)
    fastapi_app.include_router(incidents_router)
    fastapi_app.include_router(actions_router)
    fastapi_app.include_router(slo_router)
    fastapi_app.include_router(github_workflows_router)
    return fastapi_app


app = create_app()
