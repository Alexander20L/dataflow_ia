"""Registro explícito de modelos exclusivamente en el límite de composición."""

from dataflow.modules.audit.infrastructure import AuditRecord
from dataflow.modules.datasets.infrastructure import (
    DatasetDefaultRecord,
    DatasetRecord,
    ImportBindingRecord,
    ObjectRecord,
    VersionRecord,
)
from dataflow.modules.executions.infrastructure import (
    ArtifactRecord,
    ExecutionRecord,
    PlanRecord,
)
from dataflow.modules.executions.infrastructure import (
    AttemptRecord as ExecutionAttemptRecord,
)
from dataflow.modules.identity.infrastructure import AttemptRecord, SessionRecord, UserRecord
from dataflow.modules.ingestion.legacy_records import (
    LegacyArtifactRecord,
    LegacyExecutionRecord,
    LegacyVersionRecord,
)
from dataflow.modules.projects.infrastructure import ProjectRecord
from dataflow.modules.understanding.semantic_repository import (
    SemanticFamilyRecord,
    SemanticRevisionRecord,
    SemanticSaveRequest,
)
from dataflow.platform.runtime import RuntimeTransition

__all__ = [
    "AuditRecord",
    "AttemptRecord",
    "SessionRecord",
    "UserRecord",
    "ProjectRecord",
    "ArtifactRecord",
    "DatasetRecord",
    "ExecutionRecord",
    "VersionRecord",
    "DatasetDefaultRecord",
    "ImportBindingRecord",
    "ObjectRecord",
    "ExecutionAttemptRecord",
    "PlanRecord",
    "LegacyArtifactRecord",
    "LegacyExecutionRecord",
    "LegacyVersionRecord",
    "RuntimeTransition",
    "SemanticFamilyRecord",
    "SemanticRevisionRecord",
    "SemanticSaveRequest",
]
