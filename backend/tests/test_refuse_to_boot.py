"""Refuse-to-boot test: app raises VaultUnreachableError when Vault is down."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.infra.vault import VaultUnreachableError, load_secrets


def test_refuse_to_boot_when_vault_unreachable() -> None:
    """When Vault is not authenticated, load_secrets raises VaultUnreachableError."""
    with patch("app.infra.vault.hvac.Client") as mock_client:
        mock_client.return_value.is_authenticated.return_value = False

        with pytest.raises(VaultUnreachableError):
            load_secrets()
