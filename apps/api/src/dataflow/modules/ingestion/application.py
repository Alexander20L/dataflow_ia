import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol, cast
from uuid import UUID, uuid4

from dataflow.modules.datasets.public import Datasets, DatasetVersion, ObjectStore
from dataflow.modules.executions.public import Execution, Executions, ProcessingConfig, legacy_state
from dataflow.modules.ingestion.contracts import Diagnostic, IngestionSummary, PreviewPage
from dataflow.modules.ingestion.domain import ImportState, Version
from dataflow.modules.ingestion.plans import (
    analysis_fingerprint,
    build_plan,
    import_fingerprint,
    resolve_separator,
)
from dataflow.modules.quality.contracts import QualityReport
from dataflow.modules.understanding.contracts import DatasetProfile
from dataflow.modules.understanding.public import SemanticReference, SemanticService, TableReference
from dataflow.platform.errors import ApplicationError
from dataflow.platform.transactions import UnitOfWork


@dataclass(frozen=True)
class AnalysisOutput:
    profile: DatasetProfile | None
    quality: QualityReport
    parquet: bytes

    @property
    def diagnostic(self) -> Diagnostic:
        assert self.profile is not None
        return Diagnostic(profile=self.profile, quality=self.quality)


@dataclass(frozen=True)
class ReadOutput:
    parquet: bytes
    separator: str
    source_sha256: str
    row_count: int
    column_count: int


class Analyzer(Protocol):
    """Motor aislado por paso; cada llamada respeta el plazo restante del plan."""

    def read(
        self, content: bytes, separator: str, config: ProcessingConfig, timeout: float
    ) -> ReadOutput: ...
    def profile(
        self,
        table: bytes,
        separator: str,
        source_sha256: str,
        config: ProcessingConfig,
        timeout: float,
    ) -> DatasetProfile: ...
    def quality(self, table: bytes, config: ProcessingConfig, timeout: float) -> QualityReport: ...


class PreviewReader(Protocol):
    def read(
        self,
        content: bytes,
        limit: int,
        offset: int,
        rule: str | None = None,
        column: str | None = None,
    ) -> PreviewPage: ...


class ProjectAccess(Protocol):
    def require(self, owner_id: UUID, project_id: UUID, writable: bool = False) -> None: ...


def legacy_view(
    version: DatasetVersion, run: Execution, parent_version_id: UUID | None = None
) -> Version:
    return Version(
        version.id,
        version.dataset_id,
        version.project_id,
        version.number,
        version.file_name,
        version.content.sha256,
        version.content.byte_size,
        version.created_at,
        run.id,
        cast(ImportState, legacy_state(run.state)),
        run.row_count,
        run.column_count,
        run.error_code,
        run.error_message,
        run.attempts,
        version.kind,
        parent_version_id,
    )


class IngestionService:
    """Coordina una carga; datasets y executions son dueños de sus registros."""

    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        projects: ProjectAccess,
        preview: PreviewReader,
        uow: UnitOfWork,
        config: ProcessingConfig,
        quota: int,
        maximum_upload: int = 5 * 1024 * 1024,
    ) -> None:
        self.datasets, self.executions, self.objects = datasets, executions, objects
        self.projects, self.preview_reader, self.uow = projects, preview, uow
        self.config, self.quota, self.maximum_upload = config, quota, maximum_upload

    def submit(
        self,
        owner: UUID,
        project: UUID,
        name: str,
        content: bytes,
        separator: str,
        key: UUID,
        correlation: str,
    ) -> Version:
        try:
            if (
                not name.lower().endswith(".csv")
                or any(c in name for c in "/\\\x00\r\n")
                or len(name) > 255
            ):
                raise ApplicationError(
                    "CSV_REQUIRED", "Selecciona un nombre de archivo CSV válido.", 422
                )
            if not content:
                raise ApplicationError("EMPTY_FILE", "El archivo está vacío.", 422)
            if len(content) > self.maximum_upload:
                raise ApplicationError("FILE_TOO_LARGE", "El CSV supera el límite de tamaño.", 413)
            if separator not in {"auto", ",", ";", "tab"}:
                raise ApplicationError("CSV_SEPARATOR", "Separador no admitido.", 422)
            self.projects.require(owner, project)
            self.datasets.lock_owner(owner)
            fingerprint = import_fingerprint(name, hashlib.sha256(content).hexdigest(), separator)
            existing = self.executions.find_request(owner, project, "csv_import", key, fingerprint)
            if existing:
                result = legacy_view(self.datasets.get(owner, existing.version_id), existing)
                self.uow.rollback()
                return result
            self.projects.require(owner, project, writable=True)
            self.executions.ensure_capacity(owner, project, "csv_import")
            if self.datasets.used_bytes(owner) + len(content) > self.quota:
                raise ApplicationError(
                    "STORAGE_QUOTA", "Se alcanzó la cuota de archivos originales de la cuenta.", 413
                )
            version_id = uuid4()
            source = self.objects.put(
                f"originals/{owner}/{version_id}/{hashlib.sha256(content).hexdigest()}.csv", content
            )
            version = self.datasets.register(owner, project, version_id, name, source)
            plan = build_plan(
                owner, version, self.config, separator, resolve_separator(content, separator)
            )
            run = self.executions.enqueue(
                owner, project, version_id, "csv_import", key, fingerprint, plan, correlation
            )
            self.datasets.bind_import(version_id, run.id)
            self.uow.commit()
            return legacy_view(version, run)
        except Exception:
            self.uow.rollback()
            raise

    def versions(
        self, owner: UUID, project: UUID, limit: int, offset: int
    ) -> tuple[list[Version], int]:
        self.projects.require(owner, project)
        versions, total = self.datasets.versions(owner, project, limit, offset)
        return [self._view(owner, version) for version in versions], total

    def version(self, owner: UUID, version_id: UUID) -> Version:
        """Una versión por ID, aunque no esté en la página que muestra el selector."""
        return self._view(owner, self.datasets.get(owner, version_id))

    def _view(self, owner: UUID, version: DatasetVersion) -> Version:
        return legacy_view(
            version,
            self.executions.get(owner, self.datasets.binding(owner, version.id).execution_id),
            lineage.parent_version_id
            if version.kind == "derived" and (lineage := self.datasets.lineage(owner, version.id))
            else None,
        )

    def summary(self, owner: UUID) -> IngestionSummary:
        states = self.executions.counts(owner)
        return IngestionSummary(
            datasets=self.datasets.count(owner),
            versions=sum(states.values()),
            processed=states.get("succeeded", 0),
            pending=states.get("queued", 0) + states.get("running", 0),
            failed=states.get("failed", 0),
        )

    def diagnostic(self, owner: UUID, version_id: UUID) -> Diagnostic:
        version = self.datasets.get(owner, version_id)
        binding = self.datasets.binding(owner, version_id)
        run = self.executions.get(owner, binding.execution_id)
        self._ready(run)
        if binding.diagnostic_artifact_id:
            result = Diagnostic.model_validate_json(
                self.objects.read(
                    self.executions.artifact(owner, binding.diagnostic_artifact_id).content
                )
            )
        else:
            assert binding.profile_artifact_id and binding.quality_artifact_id
            result = Diagnostic(
                profile=DatasetProfile.model_validate_json(
                    self.objects.read(
                        self.executions.artifact(owner, binding.profile_artifact_id).content
                    )
                ),
                quality=QualityReport.model_validate_json(
                    self.objects.read(
                        self.executions.artifact(owner, binding.quality_artifact_id).content
                    )
                ),
            )
        if result.profile.source_sha256 != version.content.sha256:
            raise ApplicationError(
                "INTEGRITY_ERROR", "El diagnóstico no coincide con el original.", 409
            )
        return result

    def preview(
        self, owner: UUID, version_id: UUID, limit: int, offset: int, issue_id: str | None = None
    ) -> PreviewPage:
        binding = self.datasets.binding(owner, version_id)
        self._ready(self.executions.get(owner, binding.execution_id))
        rule = column = None
        if issue_id:
            issue = next(
                (
                    item
                    for item in self.diagnostic(owner, version_id).quality.issues
                    if item.id == issue_id
                ),
                None,
            )
            if not issue:
                raise ApplicationError("ISSUE_NOT_FOUND", "Incidencia no encontrada.", 404)
            rule, column = issue.rule, issue.column
        assert binding.table_artifact_id
        return self.preview_reader.read(
            self.objects.read(self.executions.artifact(owner, binding.table_artifact_id).content),
            limit,
            offset,
            rule,
            column,
        )

    def original(self, owner: UUID, version_id: UUID) -> tuple[str, bytes]:
        version = self.datasets.get(owner, version_id)
        if version.kind == "derived":
            raise ApplicationError(
                "DERIVED_HAS_NO_ORIGINAL",
                "Esta versión es derivada; descarga el original de la versión de origen.",
                409,
            )
        return version.file_name, self.objects.read(version.content)

    def cancel(self, owner: UUID, execution_id: UUID) -> Version:
        run = self.executions.get(owner, execution_id)
        binding = self.datasets.binding(owner, run.version_id)
        if run.kind != "csv_import" or binding.execution_id != execution_id:
            raise ApplicationError(
                "NOT_BASELINE_IMPORT", "Utiliza cancel-analysis para este análisis.", 409
            )
        return legacy_view(
            self.datasets.get(owner, run.version_id), self.executions.cancel(owner, execution_id)
        )

    @staticmethod
    def _ready(run: Execution) -> None:
        if run.state != "succeeded":
            raise ApplicationError(
                "RESULT_NOT_READY", "El procesamiento todavía no ha terminado correctamente.", 409
            )


class AnalysisService:
    """Fachada de casos de uso de análisis tabular fijo; no es planificación libre."""

    def __init__(
        self,
        datasets: Datasets,
        executions: Executions,
        objects: ObjectStore,
        projects: ProjectAccess,
        uow: UnitOfWork,
        config: ProcessingConfig,
        semantics: SemanticService | None = None,
    ) -> None:
        self.datasets, self.executions, self.objects = datasets, executions, objects
        self.projects, self.uow, self.config = projects, uow, config
        self.semantics = semantics

    def submit(
        self,
        owner: UUID,
        version_id: UUID,
        artifact_id: UUID,
        artifact_sha256: str,
        kind: Literal["profile_quality", "quality_only"],
        key: UUID,
        correlation: str,
        semantic_ref: SemanticReference | None = None,
    ) -> Execution:
        try:
            version = self.datasets.get(owner, version_id)
            self.datasets.lock_owner(owner)
            fingerprint = analysis_fingerprint(
                version_id, artifact_id, artifact_sha256, kind, semantic_ref
            )
            existing = self.executions.find_request(
                owner, version.project_id, "table_analysis", key, fingerprint
            )
            if existing:
                self.uow.rollback()
                return existing
            self.projects.require(owner, version.project_id, writable=True)
            table = self.executions.artifact(owner, artifact_id)
            if (
                table.version_id != version_id
                or table.kind != "table"
                or table.content.sha256 != artifact_sha256
            ):
                raise ApplicationError(
                    "INPUT_MISMATCH",
                    "La representación o su hash no corresponde a la versión.",
                    409,
                )
            if semantic_ref:
                if not self.semantics:
                    raise ApplicationError(
                        "SEMANTICS_UNAVAILABLE", "La revisión semántica no está disponible.", 503
                    )
                self.semantics.resolve_for_table(
                    owner,
                    semantic_ref,
                    TableReference(
                        version_id=version.id,
                        version_content_sha256=version.content.sha256,
                        artifact_id=table.id,
                        artifact_sha256=table.content.sha256,
                    ),
                )
            plan = build_plan(
                owner,
                version,
                self.config,
                table=table,
                analysis_kind=kind,
                semantic_ref=semantic_ref,
            )
            run = self.executions.enqueue(
                owner,
                version.project_id,
                version_id,
                "table_analysis",
                key,
                fingerprint,
                plan,
                correlation,
                table.id,
                table.content.sha256,
            )
            self.uow.commit()
            return run
        except Exception:
            self.uow.rollback()
            raise

    def quality(self, owner: UUID, execution_id: UUID) -> QualityReport:
        for artifact in self.executions.artifacts(owner, execution_id):
            if artifact.kind == "quality":
                return QualityReport.model_validate_json(self.objects.read(artifact.content))
            if artifact.kind == "legacy_diagnostic":
                return Diagnostic.model_validate_json(self.objects.read(artifact.content)).quality
        raise ApplicationError(
            "RESULT_NOT_READY", "El resultado de calidad no está disponible.", 409
        )

    def profile(self, owner: UUID, execution_id: UUID) -> DatasetProfile:
        for artifact in self.executions.artifacts(owner, execution_id):
            if artifact.kind == "profile":
                return DatasetProfile.model_validate_json(self.objects.read(artifact.content))
            if artifact.kind == "legacy_diagnostic":
                return Diagnostic.model_validate_json(self.objects.read(artifact.content)).profile
        raise ApplicationError(
            "PROFILE_NOT_AVAILABLE", "Este análisis no ha publicado un perfil.", 404
        )
