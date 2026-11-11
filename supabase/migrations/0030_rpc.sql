-- ============================================================================
-- Papeleta 29N — 0030_rpc.sql
--
-- API pública (POST /rest/v1/rpc/<función>). Todas devuelven JSON:
--   éxito -> {"ok": true, ...}
--   error -> {"error": "CÓDIGO"}
-- Los errores se devuelven en vez de lanzarse para que el contador de
-- intentos fallidos se guarde (una excepción desharía la transacción).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Ayudantes privados (esquema no expuesto por la API)
-- ---------------------------------------------------------------------------
create or replace function privado.hash_token(p_token text)
returns text
language sql immutable
set search_path = privado, extensions
as $$ select encode(extensions.digest(p_token, 'sha256'), 'hex') $$;

create or replace function privado.nueva_sesion(p_cuenta uuid)
returns text
language plpgsql security definer
set search_path = privado, extensions
as $$
declare
  v_token text := encode(extensions.gen_random_bytes(32), 'hex');
begin
  insert into privado.sesiones (token_hash, cuenta) values (privado.hash_token(v_token), p_cuenta);
  -- como mucho 20 sesiones abiertas por cuenta: se cierran las más antiguas
  delete from privado.sesiones
   where cuenta = p_cuenta
     and token_hash in (select token_hash from privado.sesiones
                         where cuenta = p_cuenta order by usada desc offset 20);
  return v_token;
end $$;

create or replace function privado.cuenta_de(p_token text)
returns uuid
language plpgsql security definer
set search_path = privado, extensions
as $$
declare
  v_hash text;
  v_cuenta uuid;
  v_usada timestamptz;
begin
  if p_token is null or p_token !~ '^[0-9a-f]{64}$' then return null; end if;
  v_hash := privado.hash_token(p_token);
  select cuenta, usada into v_cuenta, v_usada from privado.sesiones where token_hash = v_hash;
  if v_cuenta is not null and v_usada < now() - interval '1 hour' then
    update privado.sesiones set usada = now() where token_hash = v_hash;
  end if;
  return v_cuenta;
end $$;

revoke all on all functions in schema privado from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- papeleta_registrar(nombre, pass) -> {ok, token, nombre}
-- ---------------------------------------------------------------------------
create or replace function public.papeleta_registrar(p_nombre text, p_pass text)
returns json
language plpgsql security definer
set search_path = privado, extensions
as $$
declare
  v_nombre text := lower(trim(coalesce(p_nombre, '')));
  v_id uuid;
begin
  if v_nombre !~ '^[a-z0-9._-]{3,20}$' then
    return json_build_object('error', 'NOMBRE_INVALIDO');
  end if;
  if p_pass is null or char_length(p_pass) < 4 or octet_length(p_pass) > 72 then
    return json_build_object('error', 'PASS_INVALIDA');
  end if;
  -- freno contra registros masivos
  if (select count(*) from privado.cuentas where creada > now() - interval '1 hour') >= 300 then
    return json_build_object('error', 'DEMASIADOS_INTENTOS');
  end if;
  begin
    insert into privado.cuentas (nombre, pass_hash)
    values (v_nombre, extensions.crypt(p_pass, extensions.gen_salt('bf', 8)))
    returning id into v_id;
  exception when unique_violation then
    return json_build_object('error', 'NOMBRE_OCUPADO');
  end;
  return json_build_object('ok', true, 'token', privado.nueva_sesion(v_id), 'nombre', v_nombre);
end $$;

-- ---------------------------------------------------------------------------
-- papeleta_entrar(nombre, pass) -> {ok, token, nombre}
-- 10 fallos seguidos bloquean la cuenta 15 minutos.
-- ---------------------------------------------------------------------------
create or replace function public.papeleta_entrar(p_nombre text, p_pass text)
returns json
language plpgsql security definer
set search_path = privado, extensions
as $$
declare
  v_nombre text := lower(trim(coalesce(p_nombre, '')));
  c privado.cuentas%rowtype;
begin
  select * into c from privado.cuentas where nombre = v_nombre for update;
  if not found then
    return json_build_object('error', 'CREDENCIALES');
  end if;
  if c.bloqueada_hasta is not null and c.bloqueada_hasta > now() then
    return json_build_object('error', 'BLOQUEADA');
  end if;
  if p_pass is null or c.pass_hash <> extensions.crypt(p_pass, c.pass_hash) then
    if c.fallos + 1 >= 10 then
      update privado.cuentas set fallos = 0, bloqueada_hasta = now() + interval '15 minutes' where id = c.id;
    else
      update privado.cuentas set fallos = c.fallos + 1 where id = c.id;
    end if;
    return json_build_object('error', 'CREDENCIALES');
  end if;
  if c.fallos > 0 or c.bloqueada_hasta is not null then
    update privado.cuentas set fallos = 0, bloqueada_hasta = null where id = c.id;
  end if;
  return json_build_object('ok', true, 'token', privado.nueva_sesion(c.id), 'nombre', c.nombre);
end $$;

-- ---------------------------------------------------------------------------
-- papeleta_votos(token) -> {ok, nombre, votos: {partido: {n: {v, t}}}}
-- ---------------------------------------------------------------------------
create or replace function public.papeleta_votos(p_token text)
returns json
language plpgsql security definer
set search_path = privado, extensions
as $$
declare
  v_cuenta uuid := privado.cuenta_de(p_token);
begin
  if v_cuenta is null then return json_build_object('error', 'SESION'); end if;
  return json_build_object(
    'ok', true,
    'nombre', (select nombre from privado.cuentas where id = v_cuenta),
    'votos', coalesce((
      select json_object_agg(partido, m)
        from (select partido, json_object_agg(n::text, json_build_object('v', v, 't', t)) as m
                from privado.votos where cuenta = v_cuenta group by partido) s
    ), '{}'::json)
  );
end $$;

-- ---------------------------------------------------------------------------
-- papeleta_guardar(token, votos) -> {ok, guardados}
-- votos: {"pp": {"12": {"v": 1, "t": 1762870000000}}, ...}
-- Solo sobrescribe un voto si el nuevo es más reciente (t mayor).
-- ---------------------------------------------------------------------------
create or replace function public.papeleta_guardar(p_token text, p_votos jsonb)
returns json
language plpgsql security definer
set search_path = privado, extensions
as $$
declare
  v_cuenta uuid := privado.cuenta_de(p_token);
  v_filas int;
begin
  if v_cuenta is null then return json_build_object('error', 'SESION'); end if;
  if p_votos is null or jsonb_typeof(p_votos) <> 'object' then
    return json_build_object('error', 'DATOS');
  end if;

  with entradas as (
    select p.key as partido, e.key as n_txt, e.value as val
      from jsonb_each(p_votos) p
      cross join lateral jsonb_each(case when jsonb_typeof(p.value) = 'object' then p.value else '{}'::jsonb end) e
     where p.key ~ '^[a-z]{2,10}$'
  ), limpias as (
    select partido,
           case when n_txt ~ '^[0-9]{1,4}$' then n_txt::int end as n,
           case when jsonb_typeof(val) = 'object' and val->>'v' in ('-2', '-1', '0', '1', '2')
                then (val->>'v')::smallint end as v,
           case when jsonb_typeof(val) = 'object' and val->>'t' ~ '^[0-9]{1,15}$'
                then (val->>'t')::bigint end as t
      from entradas
  )
  insert into privado.votos (cuenta, partido, n, v, t)
  select v_cuenta, partido, n, v, t
    from limpias
   where n between 1 and 9999 and v is not null and t is not null
  on conflict (cuenta, partido, n) do update
     set v = excluded.v, t = excluded.t
   where excluded.t > privado.votos.t;

  get diagnostics v_filas = row_count;
  return json_build_object('ok', true, 'guardados', v_filas);
end $$;

-- ---------------------------------------------------------------------------
-- papeleta_salir(token) -> {ok}
-- ---------------------------------------------------------------------------
create or replace function public.papeleta_salir(p_token text)
returns json
language plpgsql security definer
set search_path = privado, extensions
as $$
begin
  if p_token ~ '^[0-9a-f]{64}$' then
    delete from privado.sesiones where token_hash = privado.hash_token(p_token);
  end if;
  return json_build_object('ok', true);
end $$;

-- ---------------------------------------------------------------------------
-- papeleta_borrar_cuenta(token, pass) -> {ok}
-- Borra la cuenta, sus sesiones y todos sus votos. Pide la contraseña.
-- ---------------------------------------------------------------------------
create or replace function public.papeleta_borrar_cuenta(p_token text, p_pass text)
returns json
language plpgsql security definer
set search_path = privado, extensions
as $$
declare
  v_cuenta uuid := privado.cuenta_de(p_token);
  v_hash text;
begin
  if v_cuenta is null then return json_build_object('error', 'SESION'); end if;
  select pass_hash into v_hash from privado.cuentas where id = v_cuenta;
  if p_pass is null or v_hash <> extensions.crypt(p_pass, v_hash) then
    return json_build_object('error', 'CREDENCIALES');
  end if;
  delete from privado.cuentas where id = v_cuenta;  -- cascada: sesiones y votos
  return json_build_object('ok', true);
end $$;

-- ---------------------------------------------------------------------------
-- Permisos: solo estas funciones son accesibles con la clave pública.
-- ---------------------------------------------------------------------------
revoke all on function public.papeleta_registrar(text, text)     from public;
revoke all on function public.papeleta_entrar(text, text)        from public;
revoke all on function public.papeleta_votos(text)               from public;
revoke all on function public.papeleta_guardar(text, jsonb)      from public;
revoke all on function public.papeleta_salir(text)               from public;
revoke all on function public.papeleta_borrar_cuenta(text, text) from public;

grant usage on schema public to anon, authenticated;
grant execute on function public.papeleta_registrar(text, text)     to anon, authenticated;
grant execute on function public.papeleta_entrar(text, text)        to anon, authenticated;
grant execute on function public.papeleta_votos(text)               to anon, authenticated;
grant execute on function public.papeleta_guardar(text, jsonb)      to anon, authenticated;
grant execute on function public.papeleta_salir(text)               to anon, authenticated;
grant execute on function public.papeleta_borrar_cuenta(text, text) to anon, authenticated;
