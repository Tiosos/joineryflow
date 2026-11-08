# Build context is the repository root:
#   docker build -f apps/api/Dockerfile .
# db/ has to be in the image: Makefile runs `alembic -w /db`, and app/meta.py
# reads the schema head from /db/alembic.ini (C2).

# ---- base: the WeasyPrint system libraries (C4) ----
# Every stage needs these, not just runtime: app/main.py imports weasyprint at
# process start, so the dev target (which CI runs pytest in) cannot even import
# the app without libgobject, pulled in transitively by libpango.
FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

# ---- deps: runtime dependencies only ----
FROM base AS deps
ENV PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /code
# pyproject.toml on its own, on purpose: see C8.
COPY apps/api/pyproject.toml /code/pyproject.toml
RUN pip install -e .

# ---- dev: adds the test toolchain. CI runs the suite in this target (C1). ----
FROM deps AS dev
RUN pip install -e ".[dev]"

# ---- runtime ----
FROM base AS runtime
COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPYCACHEPREFIX=/tmp/pycache \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache
WORKDIR /code
COPY apps/api /code
COPY db /db
# Upload root and font cache, writable by the unprivileged user (C6, C10).
RUN mkdir -p /uploads /tmp/.cache && chown -R 10001:10001 /uploads /tmp/.cache
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*", "--workers", "2"]
