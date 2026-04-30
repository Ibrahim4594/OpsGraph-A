# RepoPulse backend — dev image (M2.0 T9).
#
# Slim Python base + the project installed editable. Runs Alembic
# migrations on entry and then uvicorn. Used by docker-compose.dev.yml.
#
# Production hardening (multi-stage, non-root user, pinned deps via
# uv/pip-tools) lands in M4.0; this image is for the local dev stack.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# psycopg (binary) ships its own libpq; no apt-installed Postgres client
# is required. Install only what we need to compile any wheels with C
# extensions that don't ship binary builds for slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the project + dev extras. We copy pyproject.toml first so the
# pip layer is cached when only sources change.
COPY pyproject.toml /app/
COPY src /app/src
COPY migrations /app/migrations
COPY alembic.ini /app/

RUN pip install --upgrade pip && pip install -e ".[dev]"

EXPOSE 8000

# The default command runs migrations, then starts the API. Compose
# overrides this for one-shot tasks (e.g. ``alembic upgrade head``).
CMD ["sh", "-c", "alembic upgrade head && uvicorn repopulse.main:app --host 0.0.0.0 --port 8000"]
