# The hosted demo: one image, one address. Stage 1 builds the web app; stage 2 is the API, which also serves the
# built pages (AAHAR_WEB_DIST). On start it migrates, seeds the permanent DEMO factory (idempotent) and serves.
# Local development keeps using docker-compose.yml (backend/Dockerfile and apps/web/Dockerfile).

FROM node:24-alpine AS web
WORKDIR /build/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/srv/backend \
    AAHAR_ORACLE_PATH=/srv/benchmark/expected_results.yaml \
    AAHAR_BENCHMARK_RESULTS_PATH=/srv/benchmark/results/latest.json \
    AAHAR_WEB_DIST=/srv/web \
    AAHAR_ENV=prod \
    AAHAR_COOKIE_SECURE=true \
    PORT=8000
WORKDIR /srv/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install . pytest==8.3.4 hypothesis==6.123.2 && useradd --create-home --uid 10001 aahar
COPY backend/ ./
COPY benchmark/ /srv/benchmark/
COPY --from=web /build/apps/web/dist /srv/web
RUN chmod +x /srv/backend/deploy/start.sh && mkdir -p /srv/benchmark/results && chown aahar /srv/benchmark/results
USER aahar
EXPOSE 8000
CMD ["/srv/backend/deploy/start.sh"]
