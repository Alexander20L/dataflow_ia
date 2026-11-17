"""Valoración «sí va / no va» de los hallazgos del dashboard (Fase 21, ADR-038) y versión
personalizada del dashboard (Fase 26, ADR-044).

Es opcional y nunca bloquea: «keep» fija el hallazgo arriba, «drop» lo aparta a «Descartados por
ti» y «none» retira la marca. El elemento se identifica como en el dashboard
(`insight:<id>` o `exploration:<clave>`).
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

FindingVerdict = Literal["keep", "drop", "none"]


class CurationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FindingFeedbackRequest(CurationModel):
    item: str = Field(min_length=1, max_length=700)
    verdict: FindingVerdict


class FindingFeedback(CurationModel):
    item: str
    verdict: FindingVerdict
    created_at: datetime


# --- Fase 26: versión personalizada del dashboard (ADR-044, migración 0027) ---------------------
# Cada versión guardada es una revisión inmutable; la automática no cambia nunca. Los gráficos
# señalan elementos del dashboard automático (la validación de que existen y de que el gráfico
# es compatible está en `delivery/dashboard.py`).


MAX_CUSTOM_WIDGETS = 80


class CustomWidget(CurationModel):
    item: str = Field(min_length=1, max_length=700)
    type: str = Field(min_length=1, max_length=20)
    evidence_id: str | None = Field(default=None, max_length=80)  # sólo en indicadores
    title: str | None = Field(default=None, max_length=200)  # título del usuario


class CustomSection(CurationModel):
    title: str = Field(min_length=1, max_length=200)
    # Como el dashboard automático, cuya sección «Otros hallazgos» no tiene tope.
    widgets: list[CustomWidget] = Field(min_length=1, max_length=MAX_CUSTOM_WIDGETS)


class DashboardCustomizationRequest(CurationModel):
    """Guarda la versión personalizada: secciones en su orden, sólo los gráficos visibles (los
    ocultos no van), los indicadores destacados y los títulos. `expected_revision` es la
    revisión que se editó (0 si no había ninguna)."""

    expected_revision: int = Field(ge=0)
    sections: list[CustomSection] = Field(max_length=8)


class DashboardCustomization(CurationModel):
    revision: int
    dashboard_execution_id: UUID
    sections: list[CustomSection]
    created_at: datetime
