FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ app/
COPY backend/migrations/ migrations/
COPY backend/scripts/ scripts/
COPY backend/alembic.ini .
COPY frontend/ frontend/

ENV FRONTEND_DIR=/app/frontend
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS http://localhost:8000/healthz || exit 1

# Migrations, then the server. One process serves the API and the site.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
