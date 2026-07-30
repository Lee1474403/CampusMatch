FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS backend

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY backend ./backend
COPY alembic.ini ./
COPY README.md ./

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
