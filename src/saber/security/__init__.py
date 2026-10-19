"""Security utilities: secret redaction for operational logs and exported reports.

SECURITY.md requires that secrets collected from the range (tokens, keys, passwords, authorization
headers) never reach operational logs or exported reports. `redact` is the single seam every log
sink and report serializer should pass user/range-derived strings through.
"""

from saber.security.redaction import REDACTION_PLACEHOLDER, redact, redact_mapping

__all__ = ["REDACTION_PLACEHOLDER", "redact", "redact_mapping"]
