FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .

RUN pip install uv

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ghostscript \
    && rm -rf /var/lib/apt/lists/*

RUN uv pip install --system .

COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY app ./app
COPY scripts/__init__.py ./scripts/__init__.py
COPY scripts/create_admin.py ./scripts/create_admin.py

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
