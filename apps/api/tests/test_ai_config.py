"""Fase 13B: `DATAFLOW_AI_PROVIDER=auto` (por defecto) activa la IA sólo si hay clave."""

from pathlib import Path

from pydantic import SecretStr

from dataflow.bootstrap.ai import configured
from dataflow.platform.config import Settings


def settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[arg-type,call-arg]


def test_auto_is_the_default_and_needs_a_key(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for name in ("DATAFLOW_AI_PROVIDER", "DATAFLOW_AI_API_KEY", "DATAFLOW_AI_API_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)
    plain = settings()
    assert plain.ai_provider == "auto" and plain.effective_ai_provider() == "disabled"
    provider, config = configured(plain)
    assert provider is None and config.unavailable == "disabled"

    keyed = settings(ai_api_key=SecretStr("clave-de-prueba"))
    assert keyed.effective_ai_provider() == "anthropic"
    secret = tmp_path / "clave"
    secret.write_text("  \n", encoding="utf-8")
    assert settings(ai_api_key_file=secret).effective_ai_provider() == "disabled"


def test_explicit_providers_are_respected() -> None:
    assert settings(ai_provider="disabled", ai_api_key=SecretStr("k")).effective_ai_provider() == (
        "disabled"
    )
    assert settings(ai_provider="fake").effective_ai_provider() == "fake"
    explicit = settings(ai_provider="anthropic")
    assert explicit.effective_ai_provider() == "anthropic"
    assert configured(explicit)[1].unavailable == "missing_key"
