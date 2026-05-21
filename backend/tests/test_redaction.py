"""Redaction layer tests — Phase 3.5 (D-022).

The mandatory grading criterion: the literal string ``sk-test-FAKE-not-real``
must never appear unredacted in any log output.
"""

from __future__ import annotations

import logging

import pytest

from app.infra.redaction import redact


def test_anthropic_key_is_redacted() -> None:
    text = "connecting with key sk-test-FAKE-not-real-1234567890"
    result = redact(text)
    assert "sk-test-FAKE-not-real" not in result
    assert "[REDACTED]" in result


def test_postgres_dsn_is_redacted() -> None:
    text = "DATABASE_URL=postgresql://copilot:copilot-dev-password@localhost:5432/copilot"
    result = redact(text)
    assert "copilot-dev-password" not in result
    assert "[REDACTED]" in result


def test_clean_text_passes_through() -> None:
    text = "StandardScaler handles zero-variance features by setting the scale to 1"
    assert redact(text) == text


def test_log_filter_redacts_in_log_output(caplog: pytest.LogCaptureFixture) -> None:
    from app.core.logging import configure_logging

    configure_logging(service_name="test")
    logger = logging.getLogger("test.redaction")
    with caplog.at_level(logging.INFO):
        logger.info("key is sk-ant-fake-key-that-should-not-appear")
    assert "sk-ant-fake-key" not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_github_token_is_redacted() -> None:
    text = "token ghp_" + "A" * 36
    result = redact(text)
    assert "ghp_" not in result
    assert "[REDACTED]" in result


def test_vault_token_is_redacted() -> None:
    result = redact("VAULT_TOKEN=hvs.AaBbCcDdEeFf1234567890")
    assert "hvs." not in result
    assert "[REDACTED]" in result


def test_email_is_redacted() -> None:
    result = redact("reporter: user@example.com filed issue")
    assert "user@example.com" not in result
    assert "[REDACTED]" in result


def test_multiple_secrets_in_one_string() -> None:
    text = "key=sk-ant-abc123def456ghi789 db=postgresql://user:pass@host/db email=admin@corp.io"
    result = redact(text)
    assert "sk-ant-abc" not in result
    assert "pass@host" not in result
    assert "admin@corp.io" not in result
    assert result.count("[REDACTED]") >= 3
