#!/bin/sh
# Seed Vault dev mode with all required KV v2 paths.
# Idempotent: re-running is safe (KV v2 supports versioned overwrites).

set -e

export VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
export VAULT_TOKEN="${VAULT_TOKEN:-dev-only-root-token}"

echo "vault-init: waiting for vault at $VAULT_ADDR ..."
until vault status > /dev/null 2>&1; do
    sleep 1
done
echo "vault-init: vault is ready"

PREFIX="${VAULT_KV_PATH_PREFIX:-maintainer-copilot}"

echo "vault-init: writing secrets to ${PREFIX}/*"

vault kv put "secret/${PREFIX}/db" \
    url="postgresql+asyncpg://copilot:copilot-dev-password@db:5432/copilot"

vault kv put "secret/${PREFIX}/jwt" \
    signing_key="$(head -c 32 /dev/urandom | base64)" \
    algorithm="HS256" \
    access_token_lifetime_seconds="3600"

vault kv put "secret/${PREFIX}/minio" \
    endpoint="minio:9000" \
    access_key="minioadmin" \
    secret_key="minioadmin"

vault kv put "secret/${PREFIX}/redis" \
    url="redis://redis:6379/0"

vault kv put "secret/${PREFIX}/anthropic" \
    api_key="${ANTHROPIC_API_KEY:-sk-ant-dev-placeholder-replace-in-vault}"

vault kv put "secret/${PREFIX}/langfuse" \
    public_key="pk-lf-dev-placeholder" \
    secret_key="sk-lf-dev-placeholder" \
    host="http://langfuse:3000"

echo "vault-init: seeding complete"