-- Pruebas de las funciones de cuentas y votos. Se ejecutan como el rol `anon`
-- (el de la clave pública). Cualquier fallo lanza una excepción.
-- Uso: scripts/test-db.sh
\set ON_ERROR_STOP on
set role anon;

do $$
declare
  r json;
  tok text;
  tok2 text;
  i int;
begin
  -- registro
  r := public.papeleta_registrar('Julia', '1234');
  assert r->>'ok' = 'true' and r->>'nombre' = 'julia', 'registro: ' || r::text;
  tok := r->>'token';
  assert tok ~ '^[0-9a-f]{64}$', 'token con formato';
  r := public.papeleta_registrar('julia', 'otra');
  assert r->>'error' = 'NOMBRE_OCUPADO', 'nombre ocupado: ' || r::text;
  r := public.papeleta_registrar('ab', '1234');
  assert r->>'error' = 'NOMBRE_INVALIDO', 'nombre corto: ' || r::text;
  r := public.papeleta_registrar('con espacio', '1234');
  assert r->>'error' = 'NOMBRE_INVALIDO', 'nombre con espacio';
  r := public.papeleta_registrar('pepe', '123');
  assert r->>'error' = 'PASS_INVALIDA', 'contraseña corta';

  -- entrar
  r := public.papeleta_entrar('julia', 'mal');
  assert r->>'error' = 'CREDENCIALES', 'contraseña mala';
  r := public.papeleta_entrar('nadie', '1234');
  assert r->>'error' = 'CREDENCIALES', 'usuario inexistente';
  r := public.papeleta_entrar(' JULIA ', '1234');
  assert r->>'ok' = 'true', 'entrar ignora mayúsculas y espacios: ' || r::text;
  tok2 := r->>'token';

  -- guardar: dos válidos, el resto se ignora sin error
  r := public.papeleta_guardar(tok, '{"pp":{"12":{"v":1,"t":100},"13":{"v":2,"t":100},"x":{"v":1,"t":1},"14":{"v":5,"t":1},"15":{"v":1,"t":"abc"}},"PP":{"1":{"v":1,"t":1}},"vox":7}'::jsonb);
  assert r->>'ok' = 'true' and (r->>'guardados')::int = 2, 'guardar: ' || r::text;
  -- más antiguo no sobrescribe; más reciente sí (desde otra sesión)
  r := public.papeleta_guardar(tok2, '{"pp":{"12":{"v":-2,"t":50}}}'::jsonb);
  assert (r->>'guardados')::int = 0, 'voto antiguo no pisa: ' || r::text;
  r := public.papeleta_guardar(tok2, '{"pp":{"12":{"v":-2,"t":200}}}'::jsonb);
  assert (r->>'guardados')::int = 1, 'voto nuevo pisa: ' || r::text;
  r := public.papeleta_votos(tok);
  assert r->>'nombre' = 'julia', 'votos nombre';
  assert (r->'votos'->'pp'->'12'->>'v')::int = -2 and (r->'votos'->'pp'->'12'->>'t')::bigint = 200, 'votos 12: ' || r::text;
  assert (r->'votos'->'pp'->'13'->>'v')::int = 2, 'votos 13';
  assert r->'votos'->'pp'->'14' is null, 'voto inválido no guardado';
  r := public.papeleta_guardar(tok, '[1,2]'::jsonb);
  assert r->>'error' = 'DATOS', 'datos no objeto';

  -- sesiones falsas
  r := public.papeleta_votos('no-es-un-token');
  assert r->>'error' = 'SESION', 'token falso';
  r := public.papeleta_votos(repeat('a', 64));
  assert r->>'error' = 'SESION', 'token inexistente';

  -- otra cuenta no ve los votos de julia
  r := public.papeleta_registrar('amiga', 'abcd');
  r := public.papeleta_votos(r->>'token');
  assert (r->'votos')::text = '{}', 'cuenta nueva sin votos: ' || r::text;

  -- bloqueo tras 10 fallos
  for i in 1..10 loop r := public.papeleta_entrar('amiga', 'mal'); end loop;
  r := public.papeleta_entrar('amiga', 'abcd');
  assert r->>'error' = 'BLOQUEADA', 'bloqueo: ' || r::text;

  -- salir cierra solo esa sesión
  r := public.papeleta_salir(tok2);
  assert public.papeleta_votos(tok2)->>'error' = 'SESION', 'sesión cerrada';
  assert public.papeleta_votos(tok)->>'ok' = 'true', 'la otra sesión sigue';

  -- borrar cuenta
  r := public.papeleta_borrar_cuenta(tok, 'mal');
  assert r->>'error' = 'CREDENCIALES', 'borrar con contraseña mala';
  r := public.papeleta_borrar_cuenta(tok, '1234');
  assert r->>'ok' = 'true', 'borrar cuenta';
  assert public.papeleta_votos(tok)->>'error' = 'SESION', 'sesión borrada con la cuenta';
  assert (public.papeleta_entrar('julia', '1234'))->>'error' = 'CREDENCIALES', 'cuenta borrada';

  raise notice 'OK: funciones públicas';
end $$;

-- La clave pública no puede tocar las tablas ni los ayudantes privados
do $$
begin
  begin
    perform 1 from privado.cuentas;
    raise exception 'anon pudo leer privado.cuentas';
  exception when insufficient_privilege then null;
  end;
  begin
    perform privado.nueva_sesion(gen_random_uuid());
    raise exception 'anon pudo crear una sesión';
  exception when insufficient_privilege then null;
  end;
  raise notice 'OK: sin acceso directo';
end $$;

reset role;
select 'votos en la tabla tras borrar la cuenta: ' || count(*) from privado.votos v
  join privado.cuentas c on c.id = v.cuenta where c.nombre = 'julia';
