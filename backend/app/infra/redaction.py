"""Credential and PII redaction — Phase 3.5 (D-022).

Exposes one public function: `redact(text: str) -> str`.

Called before any string crosses a service boundary: log emission,
Langfuse trace/span metadata, Redis short-term memory writes, and
pgvector long-term memory writes.

Pattern list and per-pattern rationale are documented in D-022.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Compiled patterns — order matters: more specific before more general.
# ---------------------------------------------------------------------------

_PATTERNS: list[re.Pattern[str]] = [
    # Anthropic API keys: sk-ant- prefix + alphanumeric/hyphen body.
    re.compile(r"sk-ant-[A-Za-z0-9\-]+"),
    # Generic API keys: sk- + 20+ alphanum/hyphen chars.
    # Allows hyphens so sk-test-FAKE-... style test keys are also caught.
    # Placed after the Anthropic pattern so sk-ant- is already replaced.
    re.compile(r"sk-[A-Za-z0-9\-]{20,}"),
    # GitHub personal access tokens (fine-grained: github_pat_, classic: ghp_, server: ghs_).
    re.compile(r"gh[ps]_[A-Za-z0-9]{36}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{82}"),
    # HashiCorp Vault service tokens.
    re.compile(r"hvs\.[A-Za-z0-9]+"),
    # Postgres connection strings — redact the whole DSN to avoid leaking
    # hostnames, usernames, and passwords together.
    re.compile(r"postgresql://[^\s]+"),
    # JWT tokens: three base64url segments separated by dots.
    # Conservative: each segment must be 10+ chars to avoid false positives
    # on version strings or dotted identifiers (e.g. "3.14.2").
    re.compile(r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    # Email addresses — PII under GDPR and most data-protection frameworks.
    # Redacted so user-supplied issue bodies don't leak reporter addresses
    # into logs or traces.
    re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
]

_REPLACEMENT = "[REDACTED]"


def redact(text: str) -> str:
    """Replace all recognised credential and PII patterns with ``[REDACTED]``.

    Returns the input unchanged if no pattern matches (fast path for clean text).
    """
    for pattern in _PATTERNS:
        text = pattern.sub(_REPLACEMENT, text)
    return text
