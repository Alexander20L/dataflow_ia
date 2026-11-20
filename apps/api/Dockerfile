FROM python:3.12-slim
WORKDIR /app
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
# Cabeceras de proxy: uvicorn sólo confía en FORWARDED_ALLOW_IPS (por defecto 127.0.0.1, nadie
# más); producción fija la red interna de la web (ADR-052).
CMD ["sh", "-c", "alembic upgrade head && python scripts/cutover.py --apply && uvicorn dataflow.bootstrap.app:app --host 0.0.0.0 --port 8000 --limit-concurrency 32"]
