// Cuentas con nombre + contraseña y votos sincronizados en Supabase.
// Solo se incluye en la web pública (docs/index.html). build.py sustituye
// SUPABASE por {url, key} de data/supabase.json: la clave es la pública
// (anon/publishable). La seguridad está en la base de datos: el navegador
// solo puede llamar a las funciones de supabase/migrations/0030_rpc.sql.
const SUPABASE = /*__SUPABASE__*/null;
const REST = SUPABASE.rest || SUPABASE.url.replace(/\/$/, "") + "/rest/v1";

const P = window.Papeleta;
const el = document.getElementById("cuenta");
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const NOMBRE_OK = /^[a-z0-9._-]{3,20}$/;

let sesion = P.ls.get("sesion", null);          // {token, nombre}
let modo = P.ls.get("cuentaModo", "crear");     // "crear" | "entrar"
let error = "", aviso = "", ocupado = false, borrando = false;
let estado = "";                                // "", "cargando", "ok", "guardando", "offline", "error"

// ---------- llamadas a la base de datos ----------
async function rpc(fn, args, opts = {}) {
  const headers = { "Content-Type": "application/json", apikey: SUPABASE.key };
  if (SUPABASE.key.startsWith("eyJ")) headers.Authorization = "Bearer " + SUPABASE.key; // clave anon antigua (JWT)
  let r;
  try {
    r = await fetch(`${REST}/rpc/${fn}`, { method: "POST", headers, body: JSON.stringify(args), keepalive: !!opts.keepalive });
  } catch {
    return { error: "RED" };
  }
  if (!r.ok) return { error: r.status >= 500 || r.status === 0 ? "RED" : "SERVIDOR" };
  try { return await r.json(); } catch { return { error: "SERVIDOR" }; }
}

// ---------- sincronización ----------
let pend = {}, timer = null, escribiendo = false, ultimaCarga = 0;

function encolar(p, n, rec) {
  (pend[p] ||= {})[n] = rec;
  clearTimeout(timer);
  timer = setTimeout(flush, 500);
}

async function flush(opts = {}) {
  clearTimeout(timer);
  if (!sesion || escribiendo || !Object.keys(pend).length) return;
  const lote = pend;
  pend = {};
  escribiendo = true;
  setEstado("guardando");
  const r = await rpc("papeleta_guardar", { p_token: sesion.token, p_votos: lote }, opts);
  escribiendo = false;
  if (r.ok) {
    setEstado("ok");
  } else if (r.error === "SESION") {
    return caducada();
  } else {
    for (const [p, o] of Object.entries(lote)) pend[p] = Object.assign({}, o, pend[p]);
    setEstado(r.error === "RED" ? "offline" : "error");
    timer = setTimeout(flush, 8000);
    return;
  }
  if (Object.keys(pend).length) flush();
}

async function cargar() {
  if (!sesion) return;
  ultimaCarga = Date.now();
  if (estado === "") setEstado("cargando");
  const r = await rpc("papeleta_votos", { p_token: sesion.token });
  if (r.error === "SESION") return caducada();
  if (!r.ok) { setEstado(r.error === "RED" ? "offline" : "error"); return; }
  const { masNuevos } = P.fusionar(r.votos || {});
  for (const [p, o] of Object.entries(masNuevos)) for (const [n, rec] of Object.entries(o)) (pend[p] ||= {})[n] = rec;
  if (Object.keys(pend).length) await flush(); else setEstado("ok");
}

function caducada() {
  sesion = null; P.ls.set("sesion", null);
  pend = {};
  P.usarCuenta(null);
  P.cuentaTexto("Entrar");
  error = "Tu sesión ha caducado. Vuelve a entrar con tu nombre y contraseña.";
  modo = "entrar";
  setEstado("");
  P.mostrar("cuenta");
}

function setEstado(s) {
  estado = s;
  P.nota(sesion
    ? ({
        cargando: "Cargando tus votos…",
        guardando: "Guardando tus votos en tu cuenta…",
        offline: "Sin conexión: tus votos se guardan en este navegador y se subirán a tu cuenta cuando vuelva.",
        error: "No se han podido guardar tus votos en la cuenta. Se reintentará; mientras, se guardan en este navegador.",
      }[s] || `Tus votos se guardan en la cuenta «${sesion.nombre}» y los verás en cualquier dispositivo.`)
    : "Sin cuenta: tus votos se guardan solo en este navegador.");
  if (P.vista() === "cuenta") render();
}

P.alVotar((p, n, rec) => { if (sesion) encolar(p, n, rec); });
document.addEventListener("visibilitychange", () => {
  if (!sesion) return;
  if (document.visibilityState === "hidden") flush({ keepalive: true });
  else if (Date.now() - ultimaCarga > 15000) cargar();
});
addEventListener("focus", () => { if (sesion && Date.now() - ultimaCarga > 15000) cargar(); });
addEventListener("online", () => { if (sesion) cargar(); });

// ---------- entrar / salir ----------
function empezarSesion(s, nuevo) {
  sesion = s; P.ls.set("sesion", s);
  P.ls.set("sinCuenta", false);
  P.usarCuenta(s.nombre);
  P.cuentaTexto(s.nombre);
  // votos hechos en este navegador sin cuenta: pasan a la cuenta
  const anon = P.votosAnonimos();
  const nAnon = Object.values(anon).reduce((t, o) => t + Object.keys(o || {}).length, 0);
  if (nAnon) {
    P.fusionar(anon);
    P.borrarAnonimos();
    aviso = `Se han añadido a tu cuenta ${nAnon} ${nAnon === 1 ? "voto" : "votos"} que tenías en este navegador.`;
  } else {
    aviso = nuevo ? "Cuenta creada. Ya puedes votar: todo se guarda en tu cuenta." : "";
  }
  cargar();
}

async function salir() {
  const t = sesion && sesion.token, nombre = sesion && sesion.nombre;
  await flush();
  // si todo está subido, no se deja copia de los votos en este navegador
  if (nombre && !Object.keys(pend).length) P.ls.set("votos.u." + nombre, null);
  sesion = null; P.ls.set("sesion", null);
  pend = {}; aviso = ""; error = "";
  P.usarCuenta(null);
  P.cuentaTexto("Entrar");
  setEstado("");
  render();
  if (t) rpc("papeleta_salir", { p_token: t });
}

const MENSAJES = {
  NOMBRE_OCUPADO: "Ese nombre ya está cogido. Si es tuyo, elige «Ya tengo cuenta».",
  NOMBRE_INVALIDO: "El nombre debe tener de 3 a 20 letras o números, sin espacios ni tildes.",
  PASS_INVALIDA: "La contraseña debe tener al menos 4 caracteres.",
  CREDENCIALES: "Nombre o contraseña incorrectos.",
  BLOQUEADA: "Demasiados intentos fallidos. Espera 15 minutos y vuelve a probar.",
  DEMASIADOS_INTENTOS: "Se están creando muchas cuentas a la vez. Prueba dentro de un rato.",
  RED: "No hay conexión. Comprueba internet y vuelve a probar.",
};

async function enviar(e) {
  e.preventDefault();
  if (ocupado) return;
  const f = e.target;
  const nombre = f.nombre.value.trim().toLowerCase(), pass = f.pass.value;
  const errEl = el.querySelector("#c-err");
  const fallo = m => { error = m; errEl.textContent = m; };
  if (!NOMBRE_OK.test(nombre)) return fallo(MENSAJES.NOMBRE_INVALIDO);
  if (pass.length < 4) return fallo(MENSAJES.PASS_INVALIDA);
  ocupado = true; error = "";
  const btn = f.querySelector("button[type=submit]");
  btn.disabled = true; btn.textContent = "Un momento…";
  const crear = modo === "crear";
  const r = await rpc(crear ? "papeleta_registrar" : "papeleta_entrar", { p_nombre: nombre, p_pass: pass });
  ocupado = false;
  if (!r.ok) {
    btn.disabled = false; btn.textContent = crear ? "Crear cuenta" : "Entrar";
    return fallo(MENSAJES[r.error] || "No se ha podido completar. Vuelve a intentarlo.");
  }
  empezarSesion({ token: r.token, nombre: r.nombre }, crear);
  // si se han pasado votos de este navegador a la cuenta, se enseña el aviso
  P.mostrar(aviso.startsWith("Se han") ? "cuenta" : "tarjetas");
  if (P.vista() === "cuenta") render();
}

async function borrarCuenta(e) {
  e.preventDefault();
  const pass = e.target.pass.value;
  const errEl = el.querySelector("#c-err-borrar");
  const r = await rpc("papeleta_borrar_cuenta", { p_token: sesion.token, p_pass: pass });
  if (!r.ok) { errEl.textContent = r.error === "CREDENCIALES" ? "Contraseña incorrecta." : (MENSAJES[r.error] || "No se ha podido borrar."); return; }
  const nombre = sesion.nombre;
  sesion = null; P.ls.set("sesion", null); pend = {};
  P.ls.set("votos.u." + nombre, {});
  P.usarCuenta(null);
  P.cuentaTexto("Entrar");
  borrando = false;
  aviso = "";
  error = "";
  setEstado("");
  render();
  el.insertAdjacentHTML("afterbegin", `<p class="ok">Tu cuenta y tus votos se han borrado.</p>`);
}

// ---------- interfaz ----------
const PRIVACIDAD = `<p class="fine">Los votos se guardan en una base de datos (Supabase) que administra quien publicó esta web. La web solo deja leer a cada persona sus propios votos.</p>`;

function render() {
  const url = location.origin + location.pathname;
  if (sesion) {
    el.innerHTML = `
      <h2>Tu cuenta</h2>
      <p>Has entrado como <b>${esc(sesion.nombre)}</b>. Entra con el mismo nombre y contraseña desde el móvil o el ordenador y tendrás los mismos votos.</p>
      ${aviso ? `<p class="ok">${esc(aviso)}</p>` : ""}
      <p>${estado === "cargando" ? "Cargando tus votos…" : estado === "guardando" ? "Guardando…" : estado === "offline" ? "Sin conexión: tus votos se subirán cuando vuelva." : estado === "error" ? "Hay votos pendientes de subir; se reintentará." : `Tienes <b>${P.totalVotos()}</b> votos guardados en tu cuenta.`}</p>
      <button type="button" class="btn primary" id="c-ir">Seguir votando</button>
      <div class="field">
        <label for="c-url">Pásale la web a tus amigos para que se hagan su cuenta</label>
        <div class="share"><input id="c-url" readonly value="${esc(url)}"><button type="button" class="btn" id="c-copiar">Copiar</button></div>
      </div>
      <button type="button" class="link" id="c-salir">Cerrar sesión</button>
      ${borrando ? `
        <form class="form" id="c-borrar">
          <p>Se borrarán tu cuenta y todos tus votos guardados. No se puede deshacer.</p>
          <div class="field"><label for="c-pass-borrar">Escribe tu contraseña para confirmar</label>
          <input id="c-pass-borrar" name="pass" type="password" autocomplete="current-password" required></div>
          <div class="err" id="c-err-borrar"></div>
          <button class="btn" type="submit" style="color:var(--v-rf);border-color:var(--v-rf)">Borrar mi cuenta</button>
          <button type="button" class="link" id="c-no-borrar">Cancelar</button>
        </form>` : `<button type="button" class="link" id="c-borrar-ini" style="color:var(--muted)">Borrar mi cuenta</button>`}
      ${PRIVACIDAD}`;
    el.querySelector("#c-ir").onclick = () => { aviso = ""; P.mostrar("tarjetas"); };
    el.querySelector("#c-salir").onclick = salir;
    el.querySelector("#c-copiar").onclick = async e => {
      const inp = el.querySelector("#c-url");
      try { await navigator.clipboard.writeText(inp.value); e.target.textContent = "Copiado"; }
      catch { inp.select(); }
    };
    if (borrando) {
      el.querySelector("#c-borrar").onsubmit = borrarCuenta;
      el.querySelector("#c-no-borrar").onclick = () => { borrando = false; render(); };
    } else {
      el.querySelector("#c-borrar-ini").onclick = () => { borrando = true; render(); };
    }
    return;
  }
  const crear = modo === "crear";
  el.innerHTML = `
    <h2>${crear ? "Crea tu cuenta" : "Entra en tu cuenta"}</h2>
    <p>Con una cuenta tus votos se guardan y los ves desde cualquier móvil u ordenador. Solo hace falta un nombre y una contraseña.</p>
    <div class="seg" role="group" aria-label="Tipo de acceso">
      <button type="button" data-m="crear" aria-pressed="${crear}">Soy nueva/o</button>
      <button type="button" data-m="entrar" aria-pressed="${!crear}">Ya tengo cuenta</button>
    </div>
    <form class="form" id="c-form" novalidate>
      <div class="field">
        <label for="c-nombre">Nombre</label>
        <input id="c-nombre" name="nombre" autocomplete="username" autocapitalize="none" autocorrect="off" spellcheck="false" maxlength="20" required>
        ${crear ? `<small>De 3 a 20 letras o números, sin espacios ni tildes.</small>` : ""}
      </div>
      <div class="field">
        <label for="c-pass">Contraseña</label>
        <input id="c-pass" name="pass" type="password" autocomplete="${crear ? "new-password" : "current-password"}" required>
        ${crear ? `<small>Mínimo 4 caracteres. Apúntala: no se puede recuperar porque no pedimos correo.</small>` : ""}
      </div>
      <div class="err" id="c-err">${esc(error)}</div>
      <button class="btn primary" type="submit">${crear ? "Crear cuenta" : "Entrar"}</button>
    </form>
    <button type="button" class="link" id="c-sin">Seguir sin cuenta (solo en este navegador)</button>
    ${PRIVACIDAD}`;
  el.querySelectorAll(".seg button").forEach(b => b.onclick = () => {
    modo = b.dataset.m; P.ls.set("cuentaModo", modo); error = ""; render();
  });
  el.querySelector("#c-sin").onclick = () => { P.ls.set("sinCuenta", true); error = ""; P.mostrar("tarjetas"); };
  el.querySelector("#c-form").onsubmit = enviar;
}

// ---------- arranque ----------
P.activarCuentas(render);
if (sesion) {
  P.usarCuenta(sesion.nombre);
  P.cuentaTexto(sesion.nombre);
  setEstado("");
  cargar();
} else {
  P.usarCuenta(null);
  setEstado("");
  if (!P.ls.get("sinCuenta", false)) P.mostrar("cuenta");
}
