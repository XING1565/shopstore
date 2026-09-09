# syntax=docker/dockerfile:1
# infra/docker/core.Dockerfile — Marketplace Core runtime image (ops / ISSUE-0010).
#
# Build context = repository root (see infra/docker/compose.yaml). Version freeze:
# Python 3.12 / FastAPI 0.115 / SQLAlchemy 2.0 / Alembic 1.x (docs/版本清单.md,
# ISSUE-0002). No `latest` tags; the base image is python:3.12-slim.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/core

# Install the project (hatchling builds the `app` package listed in pyproject.toml).
# COPY order keeps dependency resolution cached across code-only changes.
COPY apps/core/pyproject.toml apps/core/README.md ./
COPY apps/core/app ./app
COPY apps/core/migrations ./migrations

RUN pip install --no-cache-dir .

EXPOSE 8000

# `python -m app` starts uvicorn (see apps/core/app/__main__.py).
CMD ["python", "-m", "app"]
