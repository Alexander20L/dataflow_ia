FROM python:3.12-slim
WORKDIR /app
# Fase 12B: Microsoft ODBC Driver 18 para SQL Server. Instalarlo implica aceptar su licencia
# (ACCEPT_EULA=Y), decisión de despliegue aprobada para este proyecto.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && . /etc/os-release \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/${VERSION_ID}/prod ${VERSION_CODENAME} main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
    && apt-get purge -y curl gnupg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY requirements.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip pip install -c requirements.lock .
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
RUN useradd --create-home app
RUN mkdir -p /app/.data/objects && chown -R app:app /app/.data
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python scripts/cutover.py --apply && uvicorn dataflow.bootstrap.app:app --host 0.0.0.0 --port 8000 --no-proxy-headers --limit-concurrency 32"]
