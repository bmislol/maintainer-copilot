#!/bin/sh
# Create the langfuse database alongside the default `copilot` database.
# Runs once, on first volume bootstrap. Idempotent via "IF NOT EXISTS" pattern
# expressed through DO block.

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE langfuse OWNER ${POSTGRES_USER}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse')\gexec
EOSQL

echo "postgres-init: ensured 'langfuse' database exists"