-- Pruebas de las funciones de cuentas y votos cifrados. Se ejecutan como el
-- rol `anon` (el de la clave pública). Cualquier fallo lanza una excepción.
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
  assert public.papeleta_registrar('julia', 'otra')->>'error' = 'NOMBRE_OCUPADO', 'nombre ocupado';
  assert public.papeleta_registrar('ab', '1234')->>'error' = 'NOMBRE_INVALIDO', 'nombre corto';
  assert public.papeleta_registrar('con espacio', '1234')->>'error' = 'NOMBRE_INVALIDO', 'nombre con espacio';
  assert public.papeleta_registrar('pepe', '123')->>'error' = 'PASS_INVALIDA', 'contraseña corta';

  -- entrar
  assert public.papeleta_entrar('julia', 'mal')->>'error' = 'CREDENCIALES', 'contraseña mala';
  assert public.papeleta_entrar('nadie', '1234')->>'error' = 'CREDENCIALES', 'usuario inexistente';
  r := public.papeleta_entrar(' JULIA ', '1234');
  assert r->>'ok' = 'true', 'entrar ignora mayúsculas y espacios: ' || r::text;
  tok2 := r->>'token';

  -- cuenta nueva: sin datos, versión 0
  r := public.papeleta_leer(tok);
  assert r->>'ok' = 'true' and r->>'datos' is null and (r->>'version')::int = 0, 'leer vacío: ' || r::text;

  -- escribir el primer bloque cifrado
  r := public.papeleta_escribir(tok, 'v1.QUFB.QkJC', 0);
  assert r->>'ok' = 'true' and (r->>'version')::int = 1, 'primera escritura: ' || r::text;
  -- otra sesión que leyó la versión 0 choca y recibe lo actual
  r := public.papeleta_escribir(tok2, 'v1.Q0ND.RERE', 0);
  assert r->>'error' = 'CONFLICTO' and r->>'datos' = 'v1.QUFB.QkJC' and (r->>'version')::int = 1, 'conflicto: ' || r::text;
  r := public.papeleta_escribir(tok2, 'v1.Q0ND.RERE', 1);
  assert r->>'ok' = 'true' and (r->>'version')::int = 2, 'escritura tras mezclar: ' || r::text;
  r := public.papeleta_leer(tok);
  assert r->>'datos' = 'v1.Q0ND.RERE' and (r->>'version')::int = 2, 'leer lo último: ' || r::text;
  -- formato no cifrado: rechazado
  assert public.papeleta_escribir(tok, '{"pp":{"1":{"v":2}}}', 2)->>'error' = 'DATOS', 'texto en claro rechazado';

  -- sesiones falsas
  assert public.papeleta_leer('no-es-un-token')->>'error' = 'SESION', 'token falso';
  assert public.papeleta_leer(repeat('a', 64))->>'error' = 'SESION', 'token inexistente';
  assert public.papeleta_escribir(repeat('a', 64), 'v1.QUFB.QkJC', 0)->>'error' = 'SESION', 'escribir sin sesión';

  -- otra cuenta no ve los datos de julia
  r := public.papeleta_registrar('amiga', 'abcd');
  r := public.papeleta_leer(r->>'token');
  assert r->>'datos' is null, 'cuenta nueva sin datos: ' || r::text;

  -- bloqueo tras 10 fallos
  for i in 1..10 loop r := public.papeleta_entrar('amiga', 'mal'); end loop;
  assert public.papeleta_entrar('amiga', 'abcd')->>'error' = 'BLOQUEADA', 'bloqueo';

  -- salir cierra solo esa sesión
  r := public.papeleta_salir(tok2);
  assert public.papeleta_leer(tok2)->>'error' = 'SESION', 'sesión cerrada';
  assert public.papeleta_leer(tok)->>'ok' = 'true', 'la otra sesión sigue';

  -- las funciones antiguas en claro ya no existen
  begin
    perform public.papeleta_guardar(tok, '{}'::jsonb);
    raise exception 'papeleta_guardar sigue existiendo';
  exception when undefined_function then null;
  end;

  -- borrar cuenta
  assert public.papeleta_borrar_cuenta(tok, 'mal')->>'error' = 'CREDENCIALES', 'borrar con contraseña mala';
  assert public.papeleta_borrar_cuenta(tok, '1234')->>'ok' = 'true', 'borrar cuenta';
  assert public.papeleta_leer(tok)->>'error' = 'SESION', 'sesión borrada con la cuenta';
  assert public.papeleta_entrar('julia', '1234')->>'error' = 'CREDENCIALES', 'cuenta borrada';

  raise notice 'OK: funciones públicas';
end $$;

-- La clave pública no puede tocar las tablas ni los ayudantes privados
do $$
begin
  begin
    perform 1 from privado.cifrados;
    raise exception 'anon pudo leer privado.cifrados';
  exception when insufficient_privilege then null;
  end;
  begin
    perform privado.nueva_sesion(gen_random_uuid());
    raise exception 'anon pudo crear una sesión';
  exception when insufficient_privilege then null;
  end;
  raise notice 'OK: sin acceso directo';
end $$;

-- Transición: votos antiguos en claro se devuelven una vez y se borran al cifrar
reset role;
do $$
declare
  r json;
  tok text;
  v_id uuid;
begin
  tok := (public.papeleta_registrar('antigua', 'abcd'))->>'token';
  select id into v_id from privado.cuentas where nombre = 'antigua';
  insert into privado.votos (cuenta, partido, n, v, t) values (v_id, 'pp', 12, 1, 100);
  r := public.papeleta_leer(tok);
  assert (r->'planos'->'pp'->'12'->>'v')::int = 1, 'planos devueltos: ' || r::text;
  r := public.papeleta_escribir(tok, 'v1.QUFB.QkJC', 0);
  assert r->>'ok' = 'true', 'escribir cifrado';
  assert (select count(*) from privado.votos where cuenta = v_id) = 0, 'votos en claro borrados';
  assert public.papeleta_leer(tok)->'planos' is null or (public.papeleta_leer(tok)->>'planos') is null, 'sin planos tras cifrar';
  raise notice 'OK: transición de votos en claro';
end $$;
