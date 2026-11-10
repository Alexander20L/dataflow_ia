"""Valoración «sí va / no va» de los hallazgos del dashboard (Fase 21, ADR-038).

Es opcional y nunca bloquea: «keep» fija el hallazgo arriba, «drop» lo aparta a «Descartados por
ti» y «none» retira la marca. El elemento se identifica como en el dashboard
(`insight:<id>` o `exploration:<clave>`).
"""

from datetime import datetime
from typing import Literal

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
