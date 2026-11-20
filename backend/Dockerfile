# Build context is the repo root (see docker-compose.yml) so the oracle can be copied in.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/workspace/backend \
    AAHAR_ORACLE_PATH=/workspace/benchmark/expected_results.yaml \
    AAHAR_BENCHMARK_RESULTS_PATH=/workspace/benchmark/results/latest.json

WORKDIR /workspace/backend

COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install ".[dev]"

COPY backend/ ./
COPY benchmark/ /workspace/benchmark/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
