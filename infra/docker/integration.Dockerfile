# syntax=docker/dockerfile:1
# infra/docker/integration.Dockerfile — Integration Layer test-runner image (ops / ISSUE-0010).
#
# Stage 0 note: the Integration Layer is a library (adapters / tasks / idempotency),
# not a long-running service. It is exercised via its pytest suite (mock chain:
# Core Command -> Integration Task -> Adapter -> Mock Result). This image only runs
# the tests (see infra/docker/compose.yaml `integration-tests` profile).
#
# Build context = repository root. Version freeze: Python 3.12 / httpx 0.27
# (docs/版本清单.md). No `latest` tags.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/integration

COPY apps/integration/requirements.txt apps/integration/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY apps/integration/pyproject.toml apps/integration/README.md ./
COPY apps/integration/app ./app
COPY apps/integration/tests ./tests

RUN pip install --no-cache-dir .

CMD ["pytest", "-q"]
