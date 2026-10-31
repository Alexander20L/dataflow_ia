"""Verificar inventario y hashes de objetos sin modificar datos ni crear revisiones."""

import argparse
import json

from sqlalchemy import func, select

from dataflow.bootstrap import models  # noqa: F401
from dataflow.modules.datasets.contracts import StoredObject
from dataflow.modules.datasets.infrastructure import ObjectRecord, VersionRecord
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import ArtifactRecord, ExecutionRecord, PlanRecord
from dataflow.modules.understanding.semantic_repository import SemanticRevisionRecord
from dataflow.platform.canonical import digest
from dataflow.platform.config import get_settings
from dataflow.platform.database import session_factory
from dataflow.platform.runtime import require_ready

parser = argparse.ArgumentParser()
parser.add_argument("--expect-no-semantics", action="store_true")
args = parser.parse_args()
objects = LocalObjects(get_settings().storage_path)
with session_factory() as db:
    require_ready(db)
    inventory = []
    for record in db.scalars(select(ObjectRecord).order_by(ObjectRecord.id)):
        objects.read(StoredObject(record.object_key, record.sha256, record.byte_size))
        inventory.append(
            {"object_id": str(record.id), "sha256": record.sha256, "byte_size": record.byte_size}
        )
    counts = {
        name: int(db.scalar(select(func.count()).select_from(model)) or 0)
        for name, model in [
            ("versions", VersionRecord),
            ("executions", ExecutionRecord),
            ("artifacts", ArtifactRecord),
            ("plans", PlanRecord),
        ]
    }
    semantic_count = int(db.scalar(select(func.count()).select_from(SemanticRevisionRecord)) or 0)
    if args.expect_no_semantics and semantic_count:
        raise RuntimeError("La migración no debe crear revisiones/confirmaciones semánticas.")
    print(
        json.dumps(
            {
                "inventory": {
                    **counts,
                    "objects": len(inventory),
                    "identity_sha256": digest("release_inventory", inventory),
                },
                "semantic_revisions": semantic_count,
            }
        )
    )
