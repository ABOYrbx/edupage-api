# syntax=docker/dockerfile:1

# ---- frontend build -------------------------------------------------------
# The web build is architecture-independent; build it once on the runner
# instead of emulating Node for every target platform.
FROM --platform=$BUILDPLATFORM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- runtime --------------------------------------------------------------
FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN adduser --system --uid 10001 --group edupage \
    && mkdir -p /app/data \
    && chown -R edupage:edupage /app

COPY backend/pyproject.toml ./
# Install runtime deps from pyproject (no editable install of the project itself).
RUN python -c "import tomllib;print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/reqs.txt \
    && pip install -r /tmp/reqs.txt \
    && rm /tmp/reqs.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY --from=web /web/dist /app/static
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENV FRONTEND_DIST=/app/static \
    DATA_DIR=/app/data \
    CREDENTIAL_ENCRYPTION_KEY_FILE=/app/data/credential.key

# Starts as root so the entrypoint can fix volume ownership and persist the vault
# key, then drops to the unprivileged user before running the app.
EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/api/v1/health',timeout=4).status==200 else 1)"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]
