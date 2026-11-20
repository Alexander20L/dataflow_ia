"""Copias de bases en segundo plano (Fase 33, ADR-051).

La contraseña no se guarda en ningún sitio, así que la copia no puede ser un trabajo del worker
(otro proceso que sólo lee de la cola): corre en un hilo de la API que conserva la conexión en
memoria. Su estado, sin credenciales, queda en `database_copies`. Mientras corre (o espera su
turno) late cada pocos segundos; si la API se reinicia, el latido se detiene y la copia se da
por interrumpida al consultarla.
"""

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.ingestion.application import CopyKind, CopyTicket, DatabaseEngine
from dataflow.modules.ingestion.contracts import PostgresConnection, SqlServerConnection
from dataflow.modules.ingestion.infrastructure import SQLDatabaseCopies
from dataflow.platform.config import get_settings
from dataflow.platform.database import session_factory

logger = logging.getLogger("dataflow.database_copies")
HEARTBEAT_SECONDS = 20
Job = Callable[[Session], None]


class CopyRunner(Protocol):
    def submit(self, owner: UUID, copy: UUID, job: Job) -> None: ...


class ThreadCopyRunner:
    """Hilos de la API (`DATAFLOW_DATABASE_COPY_WORKERS`); como mucho una copia en curso por
    cuenta (las demás esperan su turno en `queued`, latiendo)."""

    def __init__(self, workers: int, sessions: Callable[[], Session] = session_factory) -> None:
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="database-copy")
        self.sessions = sessions
        self.locks: defaultdict[UUID, threading.Lock] = defaultdict(threading.Lock)

    def submit(self, owner: UUID, copy: UUID, job: Job) -> None:
        stop = threading.Event()
        threading.Thread(
            target=self.beat, args=(copy, stop), name=f"copy-heartbeat-{copy}", daemon=True
        ).start()

        def run() -> None:
            try:
                with self.locks[owner], self.sessions() as db:
                    job(db)
            except Exception:  # el trabajo ya deja su error en el registro; esto es lo imprevisto
                logger.exception("database_copy.unexpected", extra={"copy": str(copy)})
            finally:
                stop.set()

        self.pool.submit(run)

    def beat(self, copy: UUID, stop: threading.Event) -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                with self.sessions() as db:
                    SQLDatabaseCopies(db).heartbeat(copy)
                    db.commit()
            except Exception:
                logger.warning("database_copy.heartbeat_failed", extra={"copy": str(copy)})


class InlineCopyRunner:
    """Para las pruebas: la copia corre en la misma petición y con la misma sesión."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def submit(self, owner: UUID, copy: UUID, job: Job) -> None:
        job(self.db)


@lru_cache
def thread_runner() -> ThreadCopyRunner:
    return ThreadCopyRunner(get_settings().database_copy_workers)


def copy_job(
    objects: LocalObjects,
    owner: UUID,
    project: UUID,
    engine: DatabaseEngine,
    kind: CopyKind,
    connection: PostgresConnection | SqlServerConnection,
    ticket: CopyTicket,
    key: UUID,
    correlation: str,
) -> Job:
    """El trabajo de una copia: con su propia sesión, el mismo servicio de ingesta que la API."""

    def job(db: Session) -> None:
        from dataflow.bootstrap.services import make_ingestion

        make_ingestion(db, objects).run_database_copy(
            owner, project, engine, kind, connection, ticket, key, correlation
        )

    return job
