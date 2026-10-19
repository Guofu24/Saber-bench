"""Secret redaction seam required by SECURITY.md (secret-in-log is masked)."""

from __future__ import annotations

import pytest

from saber.security import REDACTION_PLACEHOLDER, redact, redact_mapping


@pytest.mark.security
def test_redacts_known_secret_shapes() -> None:
    samples = [
        "Authorization: Bearer abcdef123456",
        "password=hunter2",
        "api_key: sk-ant-abcdefghijklmnop",
        "AKIAIOSFODNN7EXAMPLE in the log",
        "token=eyJhbGciOi.JpYXQiOjE.c2lnbmF0dXJl",
    ]
    for s in samples:
        out = redact(s)
        assert REDACTION_PLACEHOLDER in out, s
        for leak in ("hunter2", "sk-ant-abcdefghijklmnop", "AKIAIOSFODNN7EXAMPLE"):
            assert leak not in out


@pytest.mark.security
def test_redact_is_noop_on_clean_text() -> None:
    clean = "process powershell.exe on host ws-it-01 at 09:00"
    assert redact(clean) == clean


@pytest.mark.security
def test_redact_mapping_masks_sensitive_keys_and_values() -> None:
    event = {
        "host": "ws-it-01",
        "password": "p@ssw0rd",
        "nested": {"authorization_header": "Bearer xyz", "note": "api_key=sk-12345678901234567890"},
        "list": ["clean", "secret=topsecretvalue"],
    }
    out = redact_mapping(event)
    assert out["host"] == "ws-it-01"
    assert out["password"] == REDACTION_PLACEHOLDER
    assert out["nested"]["authorization_header"] == REDACTION_PLACEHOLDER
    assert REDACTION_PLACEHOLDER in out["nested"]["note"]
    assert "topsecretvalue" not in out["list"][1]
