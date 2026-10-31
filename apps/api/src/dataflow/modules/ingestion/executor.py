import io
from typing import Any
from uuid import UUID, uuid4, uuid5

import polars as pl

from dataflow.modules.datasets.public import Datasets, ObjectStore
from dataflow.modules.executions.public import ArtifactOutput, Executions, Lease, PreparedWork
from dataflow.modules.ingestion.application import Analyzer, ProjectAccess
from dataflow.modules.understanding.public import SemanticReference, SemanticService, TableReference
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError


class CsvExecutor:
    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        analyzer: Analyzer,
        projects: ProjectAccess,
    ) -> None:
        self.datasets, self.executions, self.objects = datasets, executions, objects
        self.analyzer, self.projects = analyzer, projects

    def prepare(self, lease: Lease) -> PreparedWork:
        run = lease.execution
        assert run.plan
        version = self.datasets.get(run.owner_id, run.version_id)
        self.projects.require(run.owner_id, run.project_id)
        input_ref = run.plan.content["input"]
        if (
            input_ref["version_id"] != str(version.id)
            or input_ref["version_content_sha256"] != version.content.sha256
        ):
            raise ApplicationError("INPUT_MISMATCH", "La versión fijada no coincide.", 409)
        read = run.plan.content["steps"][0]
        return PreparedWork(
            version.content,
            version.content.sha256,
            run.plan.config,
            read["parameters"]["separator"],
        )

    def compute(self, lease: Lease, work: PreparedWork) -> list[ArtifactOutput]:
        result = self.analyzer.analyze(
            self.objects.read(work.reference), work.separator, work.config
        )
        assert result.profile
        if result.profile.source_sha256 != work.source_sha256:
            raise ApplicationError("INTEGRITY_ERROR", "La salida no corresponde al original.", 409)
        prefix = f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}"
        table = self.objects.put(f"{prefix}/data.parquet", result.parquet)
        columns, logical_hash = table_metadata(lease.version_id, result.parquet)
        outputs = [
            ArtifactOutput(
                uuid4(),
                "read",
                "table",
                "table",
                table,
                "application/vnd.apache.parquet",
                result.profile.row_count,
                result.profile.column_count,
                columns,
                logical_hash,
            )
        ]
        outputs.extend(
            diagnostic_outputs(lease, result.profile, result.quality, self.objects, prefix)
        )
        return outputs


class TableExecutor(CsvExecutor):
    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        analyzer: Analyzer,
        projects: ProjectAccess,
        semantics: SemanticService | None = None,
    ) -> None:
        super().__init__(datasets, executions, objects, analyzer, projects)
        self.semantics = semantics

    def prepare(self, lease: Lease) -> PreparedWork:
        run = lease.execution
        assert run.plan and run.input_artifact_id
        version = self.datasets.get(run.owner_id, run.version_id)
        self.projects.require(run.owner_id, run.project_id)
        artifact = self.executions.artifact(run.owner_id, run.input_artifact_id)
        input_ref = run.plan.content["input"]
        if (
            input_ref.get("kind") != "table"
            or input_ref.get("version_id") != str(version.id)
            or artifact.kind != "table"
            or artifact.version_id != version.id
            or artifact.content.sha256 != run.input_artifact_sha256
            or input_ref.get("artifact_id") != str(artifact.id)
            or input_ref.get("artifact_sha256") != artifact.content.sha256
            or input_ref["version_content_sha256"] != version.content.sha256
        ):
            raise ApplicationError(
                "INPUT_MISMATCH", "La tabla fijada no coincide con el plan.", 409
            )
        if run.plan.content.get("semantic_ref") is not None:
            if not self.semantics:
                raise ApplicationError(
                    "SEMANTICS_UNAVAILABLE", "No se puede verificar la revisión semántica.", 409
                )
            self.semantics.resolve_for_table(
                run.owner_id,
                SemanticReference.model_validate(run.plan.content["semantic_ref"]),
                TableReference(
                    version_id=version.id,
                    version_content_sha256=version.content.sha256,
                    artifact_id=artifact.id,
                    artifact_sha256=artifact.content.sha256,
                ),
            )
        quality_only = not any(
            step["operation"] == "understanding.profile" for step in run.plan.content["steps"]
        )
        return PreparedWork(
            artifact.content, version.content.sha256, run.plan.config, ",", quality_only
        )

    def compute(self, lease: Lease, work: PreparedWork) -> list[ArtifactOutput]:
        result = self.analyzer.analyze(
            self.objects.read(work.reference),
            work.separator,
            work.config,
            work.source_sha256,
            work.quality_only,
        )
        return diagnostic_outputs(
            lease,
            result.profile,
            result.quality,
            self.objects,
            f"artifacts/{lease.owner_id}/{lease.version_id}/{lease.token}",
        )


def table_metadata(version_id: UUID, content: bytes) -> tuple[list[dict[str, Any]], str]:
    frame = pl.read_parquet(io.BytesIO(content))
    columns = [
        {
            "id": str(uuid5(version_id, f"{index}/{name}")),
            "name": name,
            "ordinal": index,
            "technical_type": "string",
            "type_parameters": {},
            "nullable": True,
        }
        for index, name in enumerate(frame.columns)
    ]
    return columns, digest(
        "table", {"columns": columns, "rows": [list(row) for row in frame.iter_rows()]}
    )


def diagnostic_outputs(
    lease: Lease, profile: Any, quality: Any, objects: ObjectStore, prefix: str
) -> list[ArtifactOutput]:
    outputs = []
    for kind, value in [("profile", profile), ("quality", quality)]:
        if value is not None:
            content = objects.put(f"{prefix}/{kind}.json", value.model_dump_json().encode())
            rows = profile.row_count if profile else quality.row_count
            columns = profile.column_count if profile else quality.cell_count // quality.row_count
            if kind == "profile":
                outputs.append(
                    ArtifactOutput(
                        uuid4(),
                        "profile",
                        "profile",
                        "profile",
                        content,
                        "application/json",
                        rows,
                        columns,
                    )
                )
            else:
                outputs.append(
                    ArtifactOutput(
                        uuid4(),
                        "quality",
                        "quality",
                        "quality",
                        content,
                        "application/json",
                        rows,
                        columns,
                    )
                )
    return outputs
