"""Pure parsing, conservative estimates, identifiers and diagnostic redaction."""

import hashlib
import json
import re
from typing import Any

from .exceptions import ValidationFailedError


def estimate_tokens(text: str) -> int:
    """Estimate conservatively as UTF-8 byte length plus 16 framing tokens; not exact."""
    return len(text.encode("utf-8")) + 16


def redact_sensitive_text(text: str) -> str:
    """Mask recognized credentials; this is not universal secret detection."""
    text = re.sub(r"(?:sk-|sk-ant-)[A-Za-z0-9_-]{8,}", "[REDACTED]", text)
    text = re.sub(r"(rediss?://)[^\s/@]+:[^\s@]+@", r"\1[REDACTED]@", text)
    return re.sub(
        r"(?i)(api[_-]?key|authorization|password|token)(\s*[:=]\s*)([^\s,;]+)",
        r"\1\2[REDACTED]",
        text,
    )


def stable_project_key(project_id: str) -> str:
    """Return a deterministic opaque filesystem/Redis-safe namespace."""
    return hashlib.sha256(project_id.encode()).hexdigest()


def parse_json_object(text: str) -> dict[str, Any]:
    """Decode one bounded bare/fenced object; reject duplicate JSON keys and extra prose."""
    if not isinstance(text, str) or len(text.encode()) > 2_000_000:
        raise ValidationFailedError("Response is missing or exceeds the 2 MB parsing limit")
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines[0] not in ("```", "```json") or lines[-1] != "```":
            raise ValidationFailedError("Expected one complete fenced JSON object")
        value = "\n".join(lines[1:-1])

    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = item
        return result

    try:
        result = json.loads(value, object_pairs_hook=pairs)
        if not isinstance(result, dict):
            raise ValueError("Expected an object")
        return result
    except (ValueError, TypeError) as exc:
        raise ValidationFailedError("Expected one valid JSON object") from exc


def safe_request_id(value: Any) -> str | None:
    """Retain a bounded SDK request identifier, excluding recognized credential-like values."""
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        return value if not value.startswith("sk-") else None
    return None
