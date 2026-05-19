"""Bootstrap configuration — loaded from environment variables.

Contains ONLY the values needed to reach Vault and start listening.
All application secrets resolve from Vault via `app.infra.vault`.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class BootstrapSettings(BaseSettings):
    """Settings loaded from environment / .env file.

    These are not secrets. Real secrets live in Vault.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Vault — how to reach it
    vault_addr: str = "http://vault:8200"
    vault_token: str = "dev-only-root-token"
    vault_kv_mount: str = "secret"
    vault_kv_path_prefix: str = "maintainer-copilot"

    # Service port (bind-side, inside container)
    api_port: int = 8000


bootstrap_settings = BootstrapSettings()
