-- ============================================================================
-- Papeleta 29N — 0010_schema.sql
--
-- Cuentas con nombre + contraseña y votos de cada cuenta. Todo vive en el
-- esquema `privado`, que la API de Supabase no expone: el navegador solo
-- llega a estos datos a través de las funciones de 0030_rpc.sql.
-- ============================================================================

create extension if not exists pgcrypto with schema extensions;

create schema if not exists privado;

create table if not exists privado.cuentas (
  id              uuid primary key default gen_random_uuid(),
  nombre          text not null unique check (nombre ~ '^[a-z0-9._-]{3,20}$'),
  pass_hash       text not null,                 -- bcrypt
  creada          timestamptz not null default now(),
  fallos          int not null default 0,        -- intentos fallidos seguidos
  bloqueada_hasta timestamptz
);

-- Sesiones: el navegador guarda el token; aquí solo su hash SHA-256.
create table if not exists privado.sesiones (
  token_hash text primary key,
  cuenta     uuid not null references privado.cuentas(id) on delete cascade,
  creada     timestamptz not null default now(),
  usada      timestamptz not null default now()
);
create index if not exists sesiones_cuenta_idx on privado.sesiones (cuenta, usada desc);

-- Un voto por cuenta y propuesta. v: -2 red flag, -1 en contra, 0 neutral,
-- 1 a favor, 2 esencial. t: milisegundos (Date.now()) del voto; gana el más reciente.
create table if not exists privado.votos (
  cuenta  uuid not null references privado.cuentas(id) on delete cascade,
  partido text not null check (partido ~ '^[a-z]{2,10}$'),
  n       int not null check (n between 1 and 9999),
  v       smallint not null check (v between -2 and 2),
  t       bigint not null,
  primary key (cuenta, partido, n)
);
