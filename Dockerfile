# Three stages: build the React app, build the Python environment and the served tables, then a slim runtime.
# CI builds and smoke-tests this image; Vercel's container runtime builds the same file for the deployed app.

FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

# --- 1. frontend -------------------------------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. backend environment + transform ----------------------------------------------------------------------
FROM python:3.12-slim AS backend
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev --no-editable
# Re-derive the served tables from the raw snapshot: the build fails if a data contract breaks.
COPY data/snapshot /app/data/snapshot
ENV WINDCAST_DATA_DIR=/app/data
RUN /opt/venv/bin/windcast check && /opt/venv/bin/windcast precompute --out /app/data/derived

# --- 3. runtime ----------------------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime
RUN useradd --no-log-init --create-home --uid 10001 app
COPY --from=backend /opt/venv /opt/venv
COPY --from=backend /app/data /app/data
COPY --from=frontend /app/frontend/dist /app/static
# Port 80 is what Vercel's container runtime routes to by default; platforms that set PORT (Heroku) override it.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    WINDCAST_DATA_DIR=/app/data \
    WINDCAST_STATIC_DIR=/app/static \
    PORT=80
USER app
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/api/health', timeout=2)"]
CMD ["sh", "-c", "exec uvicorn windcast.api:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips='*'"]
