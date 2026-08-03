FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build


FROM python:3.12-slim AS runtime

WORKDIR /app

COPY backend/pyproject.toml .

RUN pip install --no-cache-dir uv \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        ghostscript \
    && rm -rf /var/lib/apt/lists/* \
    && uv pip install --system .

COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/scripts/__init__.py ./scripts/__init__.py
COPY backend/scripts/create_admin.py ./scripts/create_admin.py

COPY --from=frontend-build /build/frontend/dist ./frontend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
