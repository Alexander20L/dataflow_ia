"""Ejecución de un paso de cálculo en un subproceso aislado, acotado y sin base de datos."""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from dataflow.platform.errors import ApplicationError


def run_isolated(
    scratch_root: Path,
    module: str,
    inputs: dict[str, bytes],
    arguments: list[str],
    outputs: list[str],
    timeout: float,
) -> dict[str, bytes]:
    """Escribe `inputs` en un directorio temporal privado, ejecuta `python -m module` con
    `--output <dir>` y devuelve los ficheros `outputs`. En `arguments`, `{dir}` se sustituye por
    ese directorio. Un `error.json` del proceso se convierte en ApplicationError; superar
    `timeout` produce PROCESSING_TIMEOUT (reintentable)."""
    scratch = scratch_root / ".work"
    scratch.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=scratch) as temporary:
        directory = Path(temporary)
        for name, content in inputs.items():
            (directory / name).write_bytes(content)
        resolved = [argument.replace("{dir}", str(directory)) for argument in arguments]
        try:
            result = subprocess.run(
                [sys.executable, "-m", module, "--output", str(directory), *resolved],
                timeout=timeout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "POLARS_MAX_THREADS": "2"},
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ApplicationError(
                "PROCESSING_TIMEOUT", "El procesamiento excedió el tiempo permitido.", 422
            ) from exc
        if result.returncode:
            error_path = directory / "error.json"
            if error_path.exists():
                error = json.loads(error_path.read_text(encoding="utf-8"))
                raise ApplicationError(
                    str(error["code"]), str(error["message"]), 422, error.get("details")
                )
            raise ApplicationError(
                "PROCESSING_ERROR", "El proceso analítico terminó sin resultado.", 422
            )
        return {name: (directory / name).read_bytes() for name in outputs}
