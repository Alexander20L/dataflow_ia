import hashlib
import os
import re
from pathlib import Path
from uuid import uuid4

from dataflow.modules.datasets.contracts import StoredObject
from dataflow.platform.errors import ApplicationError


class LocalObjects:
    """Objetos inmutables de desarrollo. Las claves nunca proceden del nombre de archivo."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        if not re.fullmatch(r"[a-zA-Z0-9/_.-]+", key) or ".." in key.split("/"):
            raise ApplicationError("INVALID_OBJECT_KEY", "Referencia de objeto no válida.", 500)
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ApplicationError("INVALID_OBJECT_KEY", "Referencia de objeto no válida.", 500)
        return path

    def put(self, key: str, content: bytes) -> StoredObject:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            # Enlace exclusivo: publicación atómica sin sobrescribir un objeto existente.
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.read_bytes() != content:
                    raise ApplicationError(
                        "OBJECT_CONFLICT", "El objeto inmutable no coincide.", 500
                    ) from None
            if os.name != "nt":
                descriptor = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)
        return StoredObject(key, hashlib.sha256(content).hexdigest(), len(content))

    def read(self, reference: StoredObject) -> bytes:
        path = self.path(reference.key)
        if path.stat().st_size != reference.byte_size:
            raise ApplicationError(
                "INTEGRITY_ERROR", "El tamaño del objeto no coincide con su referencia.", 409
            )
        content = path.read_bytes()
        if (
            len(content) != reference.byte_size
            or hashlib.sha256(content).hexdigest() != reference.sha256
        ):
            raise ApplicationError(
                "INTEGRITY_ERROR", "La verificación de integridad del archivo ha fallado.", 409
            )
        return content
