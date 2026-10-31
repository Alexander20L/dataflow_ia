import io
import json
from uuid import UUID

import polars as pl

from dataflow.modules.datasets.public import Datasets, ObjectStore
from dataflow.modules.executions.public import Executions
from dataflow.modules.projects.public import ProjectPermissions
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.modules.understanding.semantic_contracts import (
    ColumnFacts,
    KeyAssessment,
    Representation,
    TableReference,
)
from dataflow.platform.errors import ApplicationError


class SemanticRepresentationAccess:
    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        projects: ProjectPermissions,
    ) -> None:
        self.datasets, self.executions, self.objects, self.projects = (
            datasets,
            executions,
            objects,
            projects,
        )

    def resolve(self, owner: UUID, artifact: UUID, with_profile: bool = False) -> Representation:
        table = self.executions.artifact(owner, artifact)
        if table.kind != "table" or not table.columns:
            raise ApplicationError(
                "SEMANTIC_TABLE_REQUIRED",
                "Selecciona una representación tabular publicada con esquema.",
                409,
            )
        version = self.datasets.get(owner, table.version_id)
        self.projects.require(owner, version.project_id)
        columns = [ColumnFacts.model_validate(value) for value in table.columns]
        if [c.ordinal for c in columns] != list(range(len(columns))) or len(
            {c.id for c in columns}
        ) != len(columns):
            raise ApplicationError(
                "SEMANTIC_SCHEMA_MISMATCH",
                "El esquema publicado no tiene identidades/ordinales válidos.",
                409,
            )
        profile = None
        if with_profile:
            for output in self.executions.artifacts(owner, table.execution_id):
                if output.kind in {"profile", "legacy_diagnostic"}:
                    payload = json.loads(self.objects.read(output.content))
                    profile = DatasetProfile.model_validate(
                        payload["profile"] if output.kind == "legacy_diagnostic" else payload
                    )
                    if profile.source_sha256 != version.content.sha256 or [
                        c.name for c in profile.columns
                    ] != [c.name for c in columns]:
                        raise ApplicationError(
                            "SEMANTIC_PROFILE_MISMATCH",
                            "El perfil no coincide con la representación.",
                            409,
                        )
                    break
        return Representation(
            version.project_id,
            owner,
            TableReference(
                version_id=version.id,
                version_content_sha256=version.content.sha256,
                artifact_id=artifact,
                artifact_sha256=table.content.sha256,
            ),
            columns,
            profile,
        )

    def require_write(self, owner: UUID, project: UUID) -> None:
        self.projects.require(owner, project, writable=True)

    def key_facts(
        self, owner: UUID, artifact: UUID, columns: list[UUID], null_policy: str
    ) -> KeyAssessment:
        source = self.resolve(owner, artifact)
        table = self.executions.artifact(owner, artifact)
        frame = pl.read_parquet(io.BytesIO(self.objects.read(table.content)))
        indexes = {column.id: column.ordinal for column in source.columns}
        if not columns or not set(columns).issubset(indexes):
            raise ApplicationError("SEMANTIC_KEY_INVALID", "Columnas de clave no válidas.", 422)
        # Alias internos para no interpretar nombres del usuario como selectores/regex de Polars.
        keys = pl.DataFrame({f"k{i}": frame.to_series(indexes[id]) for i, id in enumerate(columns)})
        missing = pl.any_horizontal(pl.all().is_null())
        null_count = int(keys.select(missing.sum()).item())
        comparable = keys.filter(~missing) if null_policy == "reject" else keys
        return KeyAssessment(
            row_count=frame.height,
            duplicate_key_rows=comparable.height - comparable.unique().height,
            null_key_rows=null_count,
        )
