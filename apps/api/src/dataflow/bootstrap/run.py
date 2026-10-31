"""Arranque local/CI: aplicar migraciones antes de aceptar solicitudes."""

import argparse
import subprocess
import sys
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from dataflow.bootstrap.cutover import cutover
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.platform.config import get_settings
from dataflow.platform.database import session_factory
from dataflow.platform.runtime import RuntimeTransition


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--with-worker", action="store_true")
    args = parser.parse_args()
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    command.upgrade(config, "head")
    with session_factory() as db:
        transition = db.get(RuntimeTransition, 1)
        if not transition or transition.state != "active":
            cutover(db, LocalObjects(get_settings().storage_path), apply=True)
    worker = (
        subprocess.Popen([sys.executable, "-m", "dataflow.bootstrap.worker"])
        if args.with_worker
        else None
    )
    try:
        uvicorn.run(
            "dataflow.bootstrap.app:app",
            host="127.0.0.1",
            port=args.port,
            proxy_headers=False,
            access_log=False,
        )
    finally:
        if worker:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()


if __name__ == "__main__":
    main()
