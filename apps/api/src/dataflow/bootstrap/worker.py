import json
import logging
import time

from dataflow.bootstrap import models  # noqa: F401
from dataflow.bootstrap.services import make_runner
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.platform.config import get_settings
from dataflow.platform.database import session_factory

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("dataflow.worker")


def main() -> None:
    settings = get_settings()
    settings.require_ai()  # Fase 29: sin IA activa, no arranca si es obligatoria
    objects = LocalObjects(settings.storage_path)
    logger.info(json.dumps({"event": "worker.started"}))
    while True:
        try:
            with session_factory() as db:
                handled = make_runner(db, objects).run_once()
            if not handled:
                time.sleep(1)
        except KeyboardInterrupt:
            return
        except Exception as exc:
            logger.error(json.dumps({"event": "worker.error", "type": type(exc).__name__}))
            time.sleep(3)


if __name__ == "__main__":
    main()
