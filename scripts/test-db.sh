#!/usr/bin/env bash
# Prueba las migraciones de supabase/ en un Postgres 15 temporal con Docker.
# Uso: scripts/test-db.sh
set -euo pipefail
cd "$(dirname "$0")/.."

NAME=papeleta-test-db
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -e POSTGRES_PASSWORD=test postgres:15-alpine >/dev/null
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

for _ in $(seq 1 30); do
  docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1 && break
  sleep 1
done
sleep 1

psql_run() { docker exec -i "$NAME" psql -q -v ON_ERROR_STOP=1 -U postgres -d postgres "$@"; }

# Lo que Supabase ya trae: roles de la API y el esquema `extensions`.
psql_run <<'SQL'
create role anon nologin;
create role authenticated nologin;
create schema extensions;
SQL

for f in supabase/migrations/*.sql; do
  echo "· $f"
  psql_run < "$f"
done

psql_run < supabase/tests/cuentas.sql
