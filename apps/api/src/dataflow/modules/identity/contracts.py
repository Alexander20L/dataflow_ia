from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class User:
    id: UUID
    email: str
    name: str


@dataclass(frozen=True)
class SessionIdentity:
    user: User
    session_hash: str
    csrf_token: str
    expires_at: datetime
