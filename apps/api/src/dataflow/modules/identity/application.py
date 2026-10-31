import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from dataflow.modules.identity.contracts import SessionIdentity, User
from dataflow.platform.errors import ApplicationError


class Passwords(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, encoded: str, password: str) -> bool: ...


class IdentityRepository(Protocol):
    def find_credentials(self, email: str) -> tuple[User, str] | None: ...
    def create_user(self, user: User, password_hash: str) -> None: ...
    def save_session(self, identity: SessionIdentity) -> None: ...
    def find_session(self, token_hash: str) -> SessionIdentity | None: ...
    def delete_session(self, token_hash: str) -> None: ...
    def record_attempt(self, email: str, ip: str) -> bool: ...


@dataclass(frozen=True)
class IssuedSession:
    identity: SessionIdentity
    token: str


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class IdentityService:
    def __init__(self, repository: IdentityRepository, passwords: Passwords, hours: int) -> None:
        self.repository = repository
        self.passwords = passwords
        self.hours = hours

    def authenticate(
        self, email: str, password: str, ip: str, name: str | None = None
    ) -> IssuedSession:
        email = email.strip().lower()
        if not self.repository.record_attempt(email, ip):
            raise ApplicationError("RATE_LIMITED", "Demasiados intentos. Inténtalo más tarde.", 429)
        credentials = self.repository.find_credentials(email)
        if name is not None:
            if credentials:
                raise ApplicationError("ACCOUNT_UNAVAILABLE", "No se puede crear esta cuenta.", 409)
            user = User(uuid4(), email, name.strip())
            self.repository.create_user(user, self.passwords.hash(password))
        else:
            # Misma comprobación costosa aunque no exista el correo.
            encoded = credentials[1] if credentials else DUMMY_PASSWORD_HASH
            valid = self.passwords.verify(encoded, password)
            if not credentials or not valid:
                raise ApplicationError(
                    "INVALID_CREDENTIALS", "Correo o contraseña incorrectos.", 401
                )
            user = credentials[0]
        token = secrets.token_urlsafe(48)
        identity = SessionIdentity(
            user,
            token_hash(token),
            secrets.token_urlsafe(32),
            datetime.now(UTC) + timedelta(hours=self.hours),
        )
        self.repository.save_session(identity)
        return IssuedSession(identity, token)

    def current(self, token: str | None) -> SessionIdentity:
        identity = self.repository.find_session(token_hash(token)) if token else None
        if not identity or identity.expires_at <= datetime.now(UTC):
            raise ApplicationError("UNAUTHENTICATED", "Inicia sesión para continuar.", 401)
        return identity

    def logout(self, identity: SessionIdentity) -> None:
        self.repository.delete_session(identity.session_hash)


# Hash Argon2id de una contraseña aleatoria; nunca se acepta como credencial de usuario.
DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQxMjM0NTY3OA$"
    "6CbXU6jzb1O4T9PZ5WVypR7sLE4E21BCbRfOcNK5D/8"
)
