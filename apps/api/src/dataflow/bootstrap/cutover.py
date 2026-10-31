"""Copia verificable 0002 → módulos separados. Nunca reescribe objetos ni historia."""

import io
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import polars as pl
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from dataflow.modules.datasets.contracts import StoredObject
from dataflow.modules.datasets.infrastructure import (
    DatasetDefaultRecord,
    DatasetRecord,
    ImportBindingRecord,
    SQLDatasetRepository,
    VersionRecord,
)
from dataflow.modules.datasets.objects import LocalObjects
from dataflow.modules.executions.infrastructure import ArtifactRecord, ExecutionRecord
from dataflow.modules.ingestion.contracts import Diagnostic
from dataflow.modules.ingestion.executor import table_metadata
from dataflow.modules.ingestion.legacy_records import (
    LegacyArtifactRecord,
    LegacyExecutionRecord,
    LegacyVersionRecord,
)
from dataflow.modules.ingestion.plans import import_fingerprint
from dataflow.platform.canonical import digest
from dataflow.platform.errors import ApplicationError
from dataflow.platform.runtime import RuntimeTransition


def cutover(db: Session, objects: LocalObjects, apply: bool = False) -> dict[str, Any]:
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(321075402401)"))
        db.execute(
            text(
                "LOCK TABLE dataset_versions, import_executions, analysis_artifacts "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
        )
        transition = db.scalar(
            select(RuntimeTransition).where(RuntimeTransition.id == 1).with_for_update()
        )
        if not transition:
            raise ApplicationError("SCHEMA_NOT_EXPANDED", "Aplica primero la migración 0003.", 503)
        active = (
            db.scalar(
                select(func.count())
                .select_from(LegacyExecutionRecord)
                .where(LegacyExecutionRecord.state.in_(["queued", "processing"]))
            )
            or 0
        )
        if active:
            raise ApplicationError(
                "LEGACY_JOBS_ACTIVE",
                "Deja terminar o cancela los trabajos 0.3 antes del corte.",
                409,
            )
        repository = SQLDatasetRepository(db)
        source_versions = list(
            db.scalars(select(LegacyVersionRecord).order_by(LegacyVersionRecord.id))
        )
        source_runs = list(
            db.scalars(select(LegacyExecutionRecord).order_by(LegacyExecutionRecord.id))
        )
        source_artifacts = list(
            db.scalars(select(LegacyArtifactRecord).order_by(LegacyArtifactRecord.id))
        )
        if len(source_versions) != len(source_runs):
            raise ApplicationError(
                "LEGACY_INCONSISTENT", "Cada versión 0.3 debe tener su ejecución baseline.", 409
            )
        versions = {record.id: record for record in source_versions}
        runs = {record.id: record for record in source_runs}
        by_version = {record.version_id: record for record in source_runs}
        manifest_items = []
        for source in source_versions:
            dataset = db.get(DatasetRecord, source.dataset_id)
            run = by_version.get(source.id)
            if (
                not dataset
                or not run
                or run.owner_id != dataset.owner_id
                or run.project_id != dataset.project_id
            ):
                raise ApplicationError(
                    "LEGACY_SCOPE_MISMATCH",
                    "El propietario o proyecto de una versión no coincide.",
                    409,
                )
            reference = StoredObject(source.original_key, source.sha256, source.byte_size)
            objects.read(reference)
            repository.register_object(dataset.owner_id, reference, "text/csv")
            target = db.get(VersionRecord, source.id)
            if target:
                if (
                    target.dataset_id,
                    target.number,
                    target.file_name,
                    target.content_object_id,
                ) != (source.dataset_id, source.number, source.file_name, reference.object_id):
                    raise ApplicationError(
                        "MIGRATION_CONFLICT", "Una versión copiada difiere del origen.", 409
                    )
            else:
                db.add(
                    VersionRecord(
                        id=source.id,
                        dataset_id=source.dataset_id,
                        number=source.number,
                        kind="imported",
                        file_name=source.file_name,
                        content_object_id=reference.object_id,
                        created_at=source.created_at,
                    )
                )
            manifest_items.append(
                {
                    "version_id": str(source.id),
                    "sha256": source.sha256,
                    "byte_size": source.byte_size,
                }
            )
        db.flush()
        for old in source_runs:
            current = db.get(ExecutionRecord, old.id)
            source = versions[old.version_id]
            fingerprint = import_fingerprint(source.file_name, source.sha256, old.separator)
            if current:
                if (
                    current.version_id,
                    current.state,
                    current.attempt_count,
                    current.request_fingerprint,
                    current.owner_id,
                ) != (old.version_id, old.state, old.attempts, fingerprint, old.owner_id):
                    raise ApplicationError(
                        "MIGRATION_CONFLICT", "Una ejecución copiada difiere del origen.", 409
                    )
            else:
                db.add(
                    ExecutionRecord(
                        id=old.id,
                        version_id=old.version_id,
                        project_id=old.project_id,
                        owner_id=old.owner_id,
                        plan_id=None,
                        kind="csv_import",
                        request_key=old.request_key,
                        request_fingerprint=fingerprint,
                        state=old.state,
                        attempt_count=old.attempts,
                        row_count=old.row_count,
                        column_count=old.column_count,
                        error_code=old.error_code,
                        error_message=old.error_message,
                        reproducibility="legacy_partial",
                        legacy_separator=old.separator,
                        correlation_id=old.correlation_id,
                        created_at=old.created_at,
                        updated_at=old.updated_at,
                        finished_at=None,
                    )
                )
        db.flush()
        migrated: dict[Any, dict[str, Any]] = {}
        for old_artifact in source_artifacts:
            artifact_run, artifact_source = (
                runs.get(old_artifact.execution_id),
                versions.get(old_artifact.version_id),
            )
            if (
                not artifact_run
                or not artifact_source
                or artifact_run.state != "succeeded"
                or artifact_run.version_id != artifact_source.id
            ):
                raise ApplicationError(
                    "LEGACY_ARTIFACT_INVALID",
                    "Un artefacto no corresponde a una ejecución completada.",
                    409,
                )
            reference = StoredObject(
                old_artifact.object_key, old_artifact.sha256, old_artifact.byte_size
            )
            content = objects.read(reference)
            columns = logical_hash = None
            if old_artifact.kind == "parquet":
                kind, media, slot = "table", "application/vnd.apache.parquet", "table"
                columns, logical_hash = table_metadata(old_artifact.version_id, content)
                if pl.read_parquet(io.BytesIO(content)).shape != (
                    artifact_run.row_count,
                    artifact_run.column_count,
                ):
                    raise ApplicationError(
                        "LEGACY_TABLE_MISMATCH",
                        "El Parquet histórico no coincide con sus conteos.",
                        409,
                    )
            elif old_artifact.kind == "diagnostic":
                kind, media, slot = "legacy_diagnostic", "application/json", "diagnostic"
                diagnostic = Diagnostic.model_validate_json(content)
                if (
                    diagnostic.profile.source_sha256 != artifact_source.sha256
                    or diagnostic.profile.row_count != artifact_run.row_count
                    or diagnostic.profile.column_count != artifact_run.column_count
                ):
                    raise ApplicationError(
                        "LEGACY_DIAGNOSTIC_MISMATCH",
                        "El diagnóstico histórico no coincide con sus datos.",
                        409,
                    )
            else:
                raise ApplicationError(
                    "LEGACY_ARTIFACT_KIND", "Tipo de artefacto histórico desconocido.", 409
                )
            repository.register_object(artifact_run.owner_id, reference, media)
            current_artifact = db.get(ArtifactRecord, old_artifact.id)
            if current_artifact:
                if (
                    current_artifact.version_id,
                    current_artifact.execution_id,
                    current_artifact.object_id,
                    current_artifact.kind,
                ) != (
                    old_artifact.version_id,
                    old_artifact.execution_id,
                    reference.object_id,
                    kind,
                ):
                    raise ApplicationError(
                        "MIGRATION_CONFLICT", "Un artefacto copiado difiere del origen.", 409
                    )
            else:
                db.add(
                    ArtifactRecord(
                        id=old_artifact.id,
                        version_id=old_artifact.version_id,
                        execution_id=old_artifact.execution_id,
                        attempt_id=None,
                        step_id="legacy_ingest",
                        slot=slot,
                        kind=kind,
                        object_id=reference.object_id,
                        row_count=artifact_run.row_count,
                        column_count=artifact_run.column_count,
                        column_schema=columns,
                        logical_content_sha256=logical_hash,
                    )
                )
            migrated.setdefault(old_artifact.version_id, {})[slot] = old_artifact.id
            manifest_items.append(
                {
                    "artifact_id": str(old_artifact.id),
                    "sha256": old_artifact.sha256,
                    "byte_size": old_artifact.byte_size,
                }
            )
        db.flush()
        for source in source_versions:
            old = by_version[source.id]
            outputs = migrated.get(source.id, {})
            if old.state == "succeeded" and set(outputs) != {"table", "diagnostic"}:
                raise ApplicationError(
                    "LEGACY_OUTPUTS_MISSING",
                    "Una carga completada no tiene sus dos artefactos.",
                    409,
                )
            binding = db.get(ImportBindingRecord, source.id)
            expected = (old.id, outputs.get("table"), outputs.get("diagnostic"))
            if binding:
                if (
                    binding.execution_id,
                    binding.table_artifact_id,
                    binding.diagnostic_artifact_id,
                ) != expected:
                    raise ApplicationError(
                        "MIGRATION_CONFLICT", "El baseline histórico no coincide.", 409
                    )
            else:
                db.add(
                    ImportBindingRecord(
                        version_id=source.id,
                        execution_id=old.id,
                        table_artifact_id=outputs.get("table"),
                        diagnostic_artifact_id=outputs.get("diagnostic"),
                    )
                )
        if transition.state != "active":
            latest: dict[UUID, LegacyVersionRecord] = {}
            for source in source_versions:
                if "table" in migrated.get(source.id, {}) and (
                    source.dataset_id not in latest
                    or source.number > latest[source.dataset_id].number
                ):
                    latest[source.dataset_id] = source
            for dataset_id, source in latest.items():
                if not db.get(DatasetDefaultRecord, dataset_id):
                    db.add(
                        DatasetDefaultRecord(
                            dataset_id=dataset_id,
                            version_id=source.id,
                            table_artifact_id=migrated[source.id]["table"],
                            revision=1,
                        )
                    )
        manifest = {
            "legacy_versions": len(source_versions),
            "legacy_executions": len(source_runs),
            "legacy_artifacts": len(source_artifacts),
            "identity_sha256": digest("migration", manifest_items),
        }
        db.flush()
        if apply:
            if (
                transition.state == "active"
                and transition.manifest
                and transition.manifest != manifest
            ):
                raise ApplicationError(
                    "MIGRATION_MANIFEST_MISMATCH",
                    "El inventario histórico cambió después del corte.",
                    409,
                )
            if transition.state != "active":
                transition.state, transition.verified_at, transition.manifest = (
                    "active",
                    datetime.now(UTC),
                    manifest,
                )
            db.commit()
        else:
            db.rollback()
        return manifest
    except Exception:
        db.rollback()
        raise
