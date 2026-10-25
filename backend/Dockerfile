# The Vandal API for a server host (Railway, Fly, Render). One process: runs live in memory,
# jobs stream over SSE, and searches run for minutes, so it needs a host that keeps it running.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 VANDAL_DOTENV=0

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

# The host sets PORT; VANDAL_CORS_ORIGINS must name the frontend's URL.
CMD ["sh", "-c", "uv run --no-sync uvicorn vandal.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
