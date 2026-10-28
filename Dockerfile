# syntax=docker/dockerfile:1
# The app as one image (ctr-1): the built React app served by the FastAPI backend, data only under /data.
#
#   docker buildx build --platform linux/arm64,linux/amd64 \
#     --build-arg GIT_SHA=$(git rev-parse HEAD) --build-arg APP_VERSION=$(git describe --tags --always) .
#
# Runs as UID/GID 10001 with a read-only root filesystem: only /data (volume) and /tmp (tmpfs) are writable.

# ---------- frontend: built once on the build machine, the output is the same for every architecture ----------
FROM --platform=$BUILDPLATFORM node:22-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# prebuild copies the pdf.js assets into public/pdfjs, then tsc -b and vite build write dist/.
RUN npm run build

# ---------- runtime ----------
FROM python:3.13-slim@sha256:b3575dcf816cdacc5292df77a6e3e59b8941631078373a045efa2ac1e9c5c3b2 AS runtime

ARG GIT_SHA=""
ARG APP_VERSION=""
LABEL org.opencontainers.image.title="medical-records" \
      org.opencontainers.image.source="https://github.com/namsey/medical-records" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATABASE_URL=sqlite:////data/medical_records.db \
    FILES_DIR=/data/files \
    UPLOAD_DIR=/data/uploads \
    APP_COMMIT="${GIT_SHA}" \
    APP_VERSION="${APP_VERSION}"

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin app \
 && mkdir -p /data \
 && chown 10001:10001 /data \
 && chmod 700 /data

# app.config: BACKEND_ROOT = /app/backend, so FRONTEND_DIST = /app/frontend/dist.
WORKDIR /app/backend
COPY backend/requirements.txt ./
# pip is not needed at runtime, and its vendored copies of urllib3, msgpack and setuptools carry CVEs (Trivy).
RUN pip install --no-cache-dir -r requirements.txt \
 && pip uninstall --yes pip
COPY backend/alembic.ini ./
COPY backend/alembic/ ./alembic/
COPY backend/app/ ./app/
COPY --from=frontend /src/frontend/dist/ /app/frontend/dist/

USER 10001:10001
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

CMD ["python", "-m", "app", "--host", "0.0.0.0", "--port", "8000"]
