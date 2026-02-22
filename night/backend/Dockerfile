# ── Build Stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Production Stage ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS production

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY . .

# Non-root user for security
RUN addgroup --system cdss && adduser --system --group cdss
USER cdss

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--log-level", "info"]
