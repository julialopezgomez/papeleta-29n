-- ============================================================================
-- Papeleta 29N — 0020_security.sql
--
-- El navegador solo tiene la clave pública (anon/publishable). Regla:
--   anon y authenticated NO tienen acceso directo a ninguna tabla ni al
--   esquema `privado`; solo pueden ejecutar las funciones públicas de 0030.
-- ============================================================================

revoke all on schema privado from public, anon, authenticated;
revoke all on all tables in schema privado from public, anon, authenticated;
revoke all on all functions in schema privado from public, anon, authenticated;
alter default privileges in schema privado revoke all on tables from public, anon, authenticated;
alter default privileges in schema privado revoke all on functions from public, anon, authenticated;

-- En `public` las funciones nuevas no se pueden ejecutar salvo permiso explícito
-- (Postgres da EXECUTE a PUBLIC por defecto; se lo quitamos).
alter default privileges in schema public revoke execute on functions from public, anon, authenticated;

-- RLS activado y sin políticas: aunque alguien concediera un permiso por
-- error, una consulta directa no devolvería filas. Las funciones SECURITY
-- DEFINER pertenecen al rol de las migraciones (dueño de las tablas) y no
-- se ven afectadas.
alter table privado.cuentas  enable row level security;
alter table privado.sesiones enable row level security;
alter table privado.votos    enable row level security;
