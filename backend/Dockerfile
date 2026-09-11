FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build


FROM python:3.12-slim AS runtime

ARG WITTY_UID=1000
ARG WITTY_GID=1000

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
COPY backend/control_alembic.ini ./control_alembic.ini
COPY backend/control_alembic ./control_alembic
COPY backend/app ./app
COPY backend/scripts/__init__.py ./scripts/__init__.py
COPY backend/scripts/create_admin.py ./scripts/create_admin.py
COPY backend/scripts/register_tenant.py ./scripts/register_tenant.py
COPY backend/scripts/bootstrap_tenancy.py ./scripts/bootstrap_tenancy.py
COPY backend/scripts/create_control_database.py ./scripts/create_control_database.py
COPY backend/scripts/migrate_tenants.py ./scripts/migrate_tenants.py

COPY --from=frontend-build /build/frontend/dist ./frontend

RUN set -eux; \
    case "${WITTY_UID}" in \
        ''|*[!0-9]*) echo "WITTY_UID muss eine positive Ganzzahl sein" >&2; exit 1 ;; \
    esac; \
    case "${WITTY_GID}" in \
        ''|*[!0-9]*) echo "WITTY_GID muss eine positive Ganzzahl sein" >&2; exit 1 ;; \
    esac; \
    test "${WITTY_UID}" -gt 0; \
    test "${WITTY_GID}" -gt 0; \
    groupadd --gid "${WITTY_GID}" witty; \
    useradd \
        --uid "${WITTY_UID}" \
        --gid "${WITTY_GID}" \
        --home-dir /app \
        --no-create-home \
        --shell /usr/sbin/nologin \
        witty; \
    install -d \
        --owner=witty \
        --group=witty \
        /app/logs \
        /app/data/invoices

USER witty:witty

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
