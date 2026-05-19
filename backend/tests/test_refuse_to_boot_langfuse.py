"""Refuse-to-boot test: init_langfuse raises when Langfuse is unreachable."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.infra.tracing import LangfuseUnreachableError, init_langfuse
from app.infra.vault import LangfuseSecrets


def test_refuse_to_boot_when_langfuse_auth_fails() -> None:
    """init_langfuse raises when auth_check returns False."""
    fake_secrets = LangfuseSecrets(public_key="pk-fake", secret_key="sk-fake", host="http://fake")

    fake_client = MagicMock()
    fake_client.auth_check.return_value = False

    with (
        patch("app.infra.tracing.Langfuse", return_value=fake_client),
        pytest.raises(LangfuseUnreachableError),
    ):
        init_langfuse(fake_secrets)


def test_refuse_to_boot_when_langfuse_unreachable() -> None:
    """init_langfuse raises when auth_check raises (network failure)."""
    fake_secrets = LangfuseSecrets(
        public_key="pk-fake", secret_key="sk-fake", host="http://nowhere"
    )

    fake_client = MagicMock()
    fake_client.auth_check.side_effect = ConnectionError("no route to host")

    with (
        patch("app.infra.tracing.Langfuse", return_value=fake_client),
        pytest.raises(LangfuseUnreachableError),
    ):
        init_langfuse(fake_secrets)
