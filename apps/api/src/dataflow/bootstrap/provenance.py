import hashlib
import platform
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

import dataflow
from dataflow.platform.errors import ApplicationError


def environment_snapshot() -> dict[str, Any]:
    root = Path(dataflow.__file__).resolve().parent
    lock = next(
        (
            path
            for path in [Path.cwd() / "requirements.lock", root.parent.parent / "requirements.lock"]
            if path.is_file()
        ),
        None,
    )
    if lock is None:
        raise ApplicationError(
            "ENVIRONMENT_UNAVAILABLE", "No está disponible el lock de dependencias.", 503
        )
    source = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        source.update(
            path.relative_to(root).as_posix().encode() + b"\x00" + path.read_bytes() + b"\x00"
        )
    return {
        "engine_version": "csv-ingestion-1",
        "source_sha256": source.hexdigest(),
        "python_version": platform.python_version(),
        "polars_version": version("polars"),
        "dependency_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "platform": f"{sys.platform}-{platform.machine()}-{sys.byteorder}",
        "image_digest": None,
    }
