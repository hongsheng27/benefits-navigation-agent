# Backend container image.
#
# Build context is the **repository root**, not `backend/`. The application
# resolves its data files with `Path(__file__).resolve().parents[3]`, so
# `backend/` and `data/` have to keep their relative positions inside the image.
#
#   docker build -t jiezhu-backend .
#
# ECR Public rather than Docker Hub or ghcr.io on purpose. Both of those reset
# the connection from the venue network on 2026-08-02; `public.ecr.aws` (AWS's
# own Docker Hub mirror) worked. It also avoids Docker Hub pull-rate limits when
# ECS pulls the image later.
FROM public.ecr.aws/docker/library/python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv==0.9.5

WORKDIR /app/backend

# Dependencies first, so a source-only change does not reinstall them.
# `psycopg[binary]` ships wheels, so no libpq build chain is needed here.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ /app/backend/
COPY data/ /app/data/

# `data/local/` is created at startup for the SQLite database, so the runtime
# user needs to own the tree. A missing database file is not an error: the
# composition root creates it and applies every migration, including the
# Case 2 seed.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/backend/.venv/bin:$PATH"

EXPOSE 8000

# One worker, deliberately. Three separate pieces of state live in this
# process, and a second worker breaks all three:
#
#   1. `InMemorySessionStore` holds sessions on the application instance.
#   2. `llm/bedrock.py` rate-limits Bedrock with a module-level global, and the
#      competition quota is under 1 request per second per account.
#   3. Once the PostgreSQL adapters land, `adapters/postgresql/connection.py`
#      opens a pool of up to 10 RDS connections per process.
#
# Scaling out requires moving all three out of process first. Until then, keep
# this at one worker and the ECS service at one task.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
