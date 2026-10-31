from uuid import UUID

from sqlalchemy.orm import Session

from dataflow.modules.audit.infrastructure import AuditRecord


def record_event(db: Session, actor: UUID, entity: UUID, action: str, correlation: str) -> None:
    """Puerto público transaccional: el módulo llamante confirma junto a su escritura."""
    db.add(AuditRecord(actor_id=actor, entity_id=entity, action=action, correlation_id=correlation))
