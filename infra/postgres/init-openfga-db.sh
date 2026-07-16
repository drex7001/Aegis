#!/bin/bash
# Creates the separate database OpenFGA uses (same instance, isolated schema/state).
# Runs once on first postgres volume init (docker-entrypoint-initdb.d).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE DATABASE openfga;
    GRANT ALL PRIVILEGES ON DATABASE openfga TO "$POSTGRES_USER";
EOSQL
