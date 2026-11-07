"""Cifrado simétrico de secretos guardados (Fase 12B): contraseñas de conexiones."""

from cryptography.fernet import Fernet, InvalidToken

from dataflow.platform.errors import ApplicationError


class FernetCipher:
    """Fernet (AES-128-CBC + HMAC-SHA256) con la clave del servidor. El texto cifrado no
    revela la contraseña y no puede alterarse sin detectarlo."""

    def __init__(self, key: str) -> None:
        try:
            self.fernet = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ApplicationError(
                "SOURCES_KEY_INVALID",
                "La clave de cifrado de conexiones no es válida (Fernet, base64 url-safe).",
                503,
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        return self.fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self.fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ApplicationError(
                "SOURCES_KEY_MISMATCH",
                "No se puede descifrar la conexión con la clave actual; vuelve a crearla.",
                409,
            ) from exc
