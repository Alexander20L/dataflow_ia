"""Hash canónico restringido de los contratos de análisis v1."""

import hashlib
import json
import re
from typing import Any


def canonical(value: Any) -> str:
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str):
            value.encode("utf-8", errors="strict")
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int) and abs(value) <= 2**53 - 1:
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict) and all(
        isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9_]*", key) for key in value
    ):
        return (
            "{"
            + ",".join(canonical(key) + ":" + canonical(value[key]) for key in sorted(value))
            + "}"
        )
    raise ValueError("CANONICAL_UNSUPPORTED_VALUE")


def digest(domain: str, value: Any) -> str:
    return hashlib.sha256(f"dataflow:{domain}:v1\n{canonical(value)}".encode()).hexdigest()
