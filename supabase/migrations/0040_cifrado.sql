-- ============================================================================
-- Papeleta 29N — 0040_cifrado.sql
--
-- Los votos pasan a guardarse CIFRADOS en el navegador (AES-GCM con una clave
-- derivada de la contraseña de cada persona, que nunca sale del navegador).
-- La base de datos solo guarda un bloque ilegible por cuenta, así que ni quien
-- administra el proyecto puede leer los votos.
--
-- Transición: papeleta_leer devuelve también los votos antiguos en claro;
-- el navegador los cifra, los sube con papeleta_escribir y esa misma llamada
-- borra los votos en claro de la cuenta.
-- ============================================================================

create table if not exists privado.cifrados (
  cuenta      uuid primary key references privado.cuentas(id) on delete cascade,
  datos       text not null check (char_length(datos) <= 2000000),
  version     int not null default 1,
  actualizado timestamptz not null default now()
);
alter table privado.cifrados enable row level security;
revoke all on privado.cifrados from public, anon, authenticated;

-- papeleta_leer(token) -> {ok, nombre, datos|null, version, planos|null}
create or replace function public.papeleta_leer(p_token text)
returns json
language plpgsql security definer
set search_path = privado, extensions
as $$
declare
  v_cuenta uuid := privado.cuenta_de(p_token);
  c privado.cifrados%rowtype;
begin
  if v_cuenta is null then return json_build_object('error', 'SESION'); end if;
  select * into c from privado.cifrados where cuenta = v_cuenta;
  return json_build_object(
    'ok', true,
    'nombre', (select nombre from privado.cuentas where id = v_cuenta),
    'datos', c.datos,
    'version', coalesce(c.version, 0),
    'planos', (
      select json_object_agg(partido, m)
        from (select partido, json_object_agg(n::text, json_build_object('v', v, 't', t)) as m
                from privado.votos where cuenta = v_cuenta group by partido) s
    )
  );
end $$;

-- papeleta_escribir(token, datos, version_leida) -> {ok, version}
-- Solo escribe si nadie ha escrito desde la versión leída; si no, devuelve
-- {error: CONFLICTO, datos, version} para que el navegador mezcle y reintente.
create or replace function public.papeleta_escribir(p_token text, p_datos text, p_version int)
returns json
language plpgsql security definer
set search_path = privado, extensions
as $$
declare
  v_cuenta uuid := privado.cuenta_de(p_token);
  c privado.cifrados%rowtype;
begin
  if v_cuenta is null then return json_build_object('error', 'SESION'); end if;
  if p_datos is null or p_datos !~ '^v1\.[A-Za-z0-9+/=]+\.[A-Za-z0-9+/=]+$' or char_length(p_datos) > 2000000 then
    return json_build_object('error', 'DATOS');
  end if;
  select * into c from privado.cifrados where cuenta = v_cuenta for update;
  if not found then
    if coalesce(p_version, 0) <> 0 then
      return json_build_object('error', 'CONFLICTO', 'datos', null, 'version', 0);
    end if;
    begin
      insert into privado.cifrados (cuenta, datos) values (v_cuenta, p_datos);
    exception when unique_violation then
      select * into c from privado.cifrados where cuenta = v_cuenta;
      return json_build_object('error', 'CONFLICTO', 'datos', c.datos, 'version', c.version);
    end;
    delete from privado.votos where cuenta = v_cuenta;  -- adiós a los votos en claro
    return json_build_object('ok', true, 'version', 1);
  end if;
  if c.version <> p_version then
    return json_build_object('error', 'CONFLICTO', 'datos', c.datos, 'version', c.version);
  end if;
  update privado.cifrados set datos = p_datos, version = c.version + 1, actualizado = now()
   where cuenta = v_cuenta;
  delete from privado.votos where cuenta = v_cuenta;
  return json_build_object('ok', true, 'version', c.version + 1);
end $$;

-- Las funciones en claro dejan de existir: nadie puede volver a guardar votos legibles.
drop function if exists public.papeleta_guardar(text, jsonb);
drop function if exists public.papeleta_votos(text);

revoke all on function public.papeleta_leer(text) from public;
revoke all on function public.papeleta_escribir(text, text, int) from public;
grant execute on function public.papeleta_leer(text) to anon, authenticated;
grant execute on function public.papeleta_escribir(text, text, int) to anon, authenticated;

notify pgrst, 'reload schema';
