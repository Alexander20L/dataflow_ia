"""Registro explícito de modelos exclusivamente en el límite de composición."""

from dataflow.modules.analysis_sessions.infrastructure import (
    AnalysisSessionInputRecord,
    AnalysisSessionRecord,
)
from dataflow.modules.analytics.infrastructure import (
    MetricFamilyRecord,
    MetricRevisionRecord,
    MetricSaveRequest,
)
from dataflow.modules.audit.infrastructure import AuditRecord
from dataflow.modules.automation.infrastructure import (
    AutomationApprovalRecord,
    AutomationPolicyFamilyRecord,
    AutomationPolicyRevisionRecord,
    AutomationPolicySaveRequest,
)
from dataflow.modules.automation.pipeline_infrastructure import (
    AutomationRunAnalysisRecord,
    AutomationRunInterpretationRecord,
    AutomationRunRecord,
    AutomationStepAttemptRecord,
)
from dataflow.modules.cleaning.repository import CleaningApprovalRecord
from dataflow.modules.copilot.infrastructure import (
    ActionLinkRecord,
    AICallRecord,
    ConversationRecord,
    CopilotRequest,
    MessageRecord,
    TextAuditRecord,
)
from dataflow.modules.dashboards.infrastructure import (
    DashboardFamilyRecord,
    DashboardRevisionRecord,
    DashboardSaveRequest,
)
from dataflow.modules.datasets.infrastructure import (
    DatasetDefaultRecord,
    DatasetRecord,
    ImportBindingRecord,
    ObjectRecord,
    VersionLineageRecord,
    VersionRecord,
)
from dataflow.modules.executions.infrastructure import (
    ArtifactRecord,
    ExecutionRecord,
    PlanBindingRecord,
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
from dataflow.modules.planning.infrastructure import (
    PlanningCreateRequest,
    PlanningValidationRecord,
)
from dataflow.modules.projects.infrastructure import ProjectRecord
from dataflow.modules.quality.infrastructure import (
    QualityRulesetFamilyRecord,
    QualityRulesetRevisionRecord,
    QualityRulesetSaveRequest,
)
from dataflow.modules.reports.infrastructure import (
    ReportFamilyRecord,
    ReportRenderRecord,
    ReportRevisionRecord,
    ReportSaveRequest,
)
from dataflow.modules.templates.infrastructure import (
    TemplateMappingFamilyRecord,
    TemplateMappingRevisionRecord,
    TemplateMappingSaveRequest,
)
from dataflow.modules.understanding.semantic_repository import (
    SemanticFamilyRecord,
    SemanticRevisionRecord,
    SemanticSaveRequest,
)
from dataflow.platform.runtime import RuntimeTransition

__all__ = [
    "AuditRecord",
    "CleaningApprovalRecord",
    "VersionLineageRecord",
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
    "PlanBindingRecord",
    "PlanRecord",
    "PlanningCreateRequest",
    "PlanningValidationRecord",
    "LegacyArtifactRecord",
    "LegacyExecutionRecord",
    "LegacyVersionRecord",
    "RuntimeTransition",
    "SemanticFamilyRecord",
    "SemanticRevisionRecord",
    "SemanticSaveRequest",
    "QualityRulesetFamilyRecord",
    "QualityRulesetRevisionRecord",
    "QualityRulesetSaveRequest",
    "MetricFamilyRecord",
    "MetricRevisionRecord",
    "MetricSaveRequest",
    "DashboardFamilyRecord",
    "DashboardRevisionRecord",
    "DashboardSaveRequest",
    "ReportFamilyRecord",
    "ReportRevisionRecord",
    "ReportSaveRequest",
    "ReportRenderRecord",
    "ConversationRecord",
    "AICallRecord",
    "MessageRecord",
    "TextAuditRecord",
    "ActionLinkRecord",
    "CopilotRequest",
    "AnalysisSessionRecord",
    "AnalysisSessionInputRecord",
    "AutomationPolicyFamilyRecord",
    "AutomationPolicyRevisionRecord",
    "AutomationPolicySaveRequest",
    "AutomationApprovalRecord",
    "AutomationRunRecord",
    "AutomationRunInterpretationRecord",
    "AutomationRunAnalysisRecord",
    "AutomationStepAttemptRecord",
    "TemplateMappingFamilyRecord",
    "TemplateMappingRevisionRecord",
    "TemplateMappingSaveRequest",
]
