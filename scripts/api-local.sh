#!/usr/bin/env bash
# Levanta en local una réplica mínima de la API de Supabase (Postgres 15 +
# PostgREST) con las migraciones de supabase/, en http://localhost:3000.
# Uso: scripts/api-local.sh start | stop
set -euo pipefail
cd "$(dirname "$0")/.."
NET=papeleta-net DB=papeleta-db API=papeleta-api

if [ "${1:-start}" = "stop" ]; then
  docker rm -f "$API" "$DB" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  echo "parada"; exit 0
fi

docker rm -f "$API" "$DB" >/dev/null 2>&1 || true
docker network create "$NET" >/dev/null 2>&1 || true
docker run -d --name "$DB" --network "$NET" -e POSTGRES_PASSWORD=test postgres:15-alpine >/dev/null
for _ in $(seq 1 30); do docker exec "$DB" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
sleep 1
psql_run() { docker exec -i "$DB" psql -q -v ON_ERROR_STOP=1 -U postgres -d postgres "$@"; }
psql_run <<'SQL'
create role anon nologin;
create role authenticated nologin;
create role authenticator login password 'auth' noinherit;
grant anon, authenticated to authenticator;
create schema extensions;
SQL
for f in supabase/migrations/*.sql; do psql_run < "$f"; done
docker run -d --name "$API" --network "$NET" -p 3000:3000 \
  -e PGRST_DB_URI="postgres://authenticator:auth@$DB:5432/postgres" \
  -e PGRST_DB_SCHEMAS=public -e PGRST_DB_ANON_ROLE=anon \
  postgrest/postgrest:v12.2.3 >/dev/null
for _ in $(seq 1 30); do curl -s -o /dev/null http://localhost:3000/ && break; sleep 1; done
echo "API local en http://localhost:3000"
