# The app as one image (built and pushed to GHCR by CI, Q60): frontend build, then the FastAPI
# backend serving it with the committed data snapshot (deploy/data/). Port: $PORT, default 8080.

FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
# --no-cache: keep uv's download cache (~670 MB) out of the image
RUN uv sync --frozen --no-dev --no-install-project --no-cache
COPY backend/ backend/
COPY pipeline/ pipeline/
COPY deploy/data/ deploy/data/
COPY docs/methodology.md docs/methodology.md
COPY --from=frontend /app/frontend/dist frontend/dist
ENV PATH=/app/.venv/bin:$PATH GREEN_PLANNER_DATA_DIR=/app/deploy/data
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
