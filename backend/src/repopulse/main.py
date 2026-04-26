"""FastAPI application entry point."""
from fastapi import FastAPI

from repopulse import __version__
from repopulse.api.health import router as health_router

app = FastAPI(
    title="RepoPulse AIOps",
    version=__version__,
)
app.include_router(health_router)
