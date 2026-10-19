"""Pattern-based secret redaction. Conservative: masks well-known secret shapes, keeps structure."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTION_PLACEHOLDER = "***REDACTED***"

# Ordered (name, pattern) rules. Each match's secret portion is replaced by the placeholder.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("bearer", re.compile(r"(?i)\b(bearer|token|authorization)\b\s*[:=]\s*\S+")),
    (
        "password_kv",
        re.compile(r"(?i)\b(pass(word|wd)?|secret|api[_-]?key|private[_-]?key)\b\s*[:=]\s*\S+"),
    ),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b")),
    (
        "pem",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL
        ),
    ),
)

# Keys whose values are always masked regardless of shape.
_SENSITIVE_KEYS = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key|authorization|credential)"
)


def redact(text: str) -> str:
    """Return `text` with recognised secret shapes masked. Safe on non-secret text (no-op)."""
    if not text:
        return text
    out = text
    for _name, pattern in _PATTERNS:
        out = pattern.sub(lambda m: _mask(m.group(0)), out)
    return out


def _mask(matched: str) -> str:
    # Preserve a key=/key: prefix so logs stay readable; mask only the value side.
    m = re.match(r"(?i)^(\s*[\w-]+\s*[:=]\s*)(.+)$", matched)
    if m:
        return m.group(1) + REDACTION_PLACEHOLDER
    return REDACTION_PLACEHOLDER


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively redact a JSON-like mapping: sensitive keys masked, string values scrubbed."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(key, str) and _SENSITIVE_KEYS.search(key):
            out[key] = REDACTION_PLACEHOLDER
        else:
            out[key] = _redact_value(value)
    return out


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value
