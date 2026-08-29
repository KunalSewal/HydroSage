FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgdal-dev gdal-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic

EXPOSE 8000

# Applies pending migrations before every start, not just the first --
# alembic upgrade head is a no-op once a migration's already applied, so
# this is safe on restarts too. Without this, a fresh deployment's DB has
# no schema at all until someone remembers to run it manually.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
