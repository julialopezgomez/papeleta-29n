// Cuentas con nombre + contraseña y votos sincronizados en Supabase.
// Solo se incluye en la web pública (docs/index.html). build.py sustituye
// SUPABASE por {url, key} de data/supabase.json: la clave es la pública
// (anon/publishable). El navegador solo puede llamar a las funciones de
// supabase/migrations/ y los votos viajan y se guardan cifrados (0040).
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
  if (r.status === 404) return { error: "NO_INSTALADO" }; // faltan las funciones en Supabase
  if (!r.ok) return { error: r.status >= 500 || r.status === 0 ? "RED" : "SERVIDOR" };
  try { return await r.json(); } catch { return { error: "SERVIDOR" }; }
}

// ---------- cifrado ----------
// Los votos se cifran en el navegador con AES-GCM. La clave se deriva de la
// contraseña (PBKDF2) y no sale nunca del navegador: la base de datos solo
// guarda un bloque ilegible ("v1.<iv>.<datos>").
const b64 = buf => btoa(String.fromCharCode(...new Uint8Array(buf)));
const deb64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));

async function derivarClave(nombre, pass) {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(pass), "PBKDF2", false, ["deriveKey"]);
  const clave = await crypto.subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", iterations: 310000, salt: new TextEncoder().encode("papeleta29n|cifrado|" + nombre) },
    base, { name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]);
  return b64(await crypto.subtle.exportKey("raw", clave));
}
let claveCache = null;
async function clave() {
  if (!claveCache || claveCache.b64 !== sesion.clave) {
    claveCache = { b64: sesion.clave, k: await crypto.subtle.importKey("raw", deb64(sesion.clave), "AES-GCM", false, ["encrypt", "decrypt"]) };
  }
  return claveCache.k;
}
async function cifrar(obj) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await clave(), new TextEncoder().encode(JSON.stringify(obj)));
  return `v1.${b64(iv)}.${b64(ct)}`;
}
async function descifrar(datos) {
  if (!datos) return {};
  const [ver, iv, ct] = datos.split(".");
  if (ver !== "v1") throw new Error("formato");
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: deb64(iv) }, await clave(), deb64(ct));
  return JSON.parse(new TextDecoder().decode(pt));
}

// ---------- sincronización ----------
// Se guarda el conjunto completo de votos como un bloque cifrado. `version`
// evita que dos dispositivos se pisen: si alguien escribió antes, se mezcla
// (gana el voto más reciente) y se reintenta.
let version = 0, sucio = false, timer = null, escribiendo = false, ultimaCarga = 0, bloqueado = false;

function encolar() {
  sucio = true;
  clearTimeout(timer);
  timer = setTimeout(flush, 600);
}

async function flush() {
  clearTimeout(timer);
  if (!sesion || escribiendo || !sucio || bloqueado) return;
  escribiendo = true;
  sucio = false;
  setEstado("guardando");
  let r;
  for (let intento = 0; intento < 4; intento++) {
    r = await rpc("papeleta_escribir", { p_token: sesion.token, p_datos: await cifrar(P.todos()), p_version: version });
    if (r.error !== "CONFLICTO") break;
    try { P.fusionar(await descifrar(r.datos)); } catch { r = { error: "CLAVE" }; break; }
    version = r.version;
  }
  escribiendo = false;
  if (r.ok) { version = r.version; setEstado("ok"); if (sucio) flush(); return; }
  if (r.error === "SESION") return caducada();
  if (r.error === "CLAVE") return claveIncorrecta();
  sucio = true;
  setEstado(r.error === "RED" ? "offline" : "error");
  timer = setTimeout(flush, 8000);
}

async function cargar() {
  if (!sesion) return;
  ultimaCarga = Date.now();
  if (estado === "") setEstado("cargando");
  const r = await rpc("papeleta_leer", { p_token: sesion.token });
  if (r.error === "SESION") return caducada();
  if (!r.ok) { setEstado(r.error === "RED" ? "offline" : "error"); return; }
  let remoto;
  try { remoto = await descifrar(r.datos); } catch { return claveIncorrecta(); }
  version = r.version;
  const a = P.fusionar(remoto);
  const b = r.planos ? P.fusionar(r.planos) : { nuevosLocales: 0 };
  // hay que subir si este dispositivo tiene algo que el servidor no, o si
  // quedan votos antiguos en claro (al subir el bloque cifrado se borran)
  if (a.nuevosLocales || r.planos || !r.datos && P.totalVotos()) { sucio = true; await flush(); }
  else setEstado("ok");
}

// Si el bloque no se puede descifrar, NO se sobrescribe (se perderían votos).
function claveIncorrecta() {
  bloqueado = true;
  setEstado("error");
  P.nota("No se han podido descifrar tus votos guardados. Cierra sesión y vuelve a entrar con tu contraseña.");
}

function caducada() {
  sesion = null; P.ls.set("sesion", null);
  sucio = false; version = 0; bloqueado = false;
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

P.alVotar(() => { if (sesion) encolar(); });
document.addEventListener("visibilitychange", () => {
  if (!sesion) return;
  if (document.visibilityState === "hidden") flush();
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
  if (nombre && !sucio) P.ls.set("votos.u." + nombre, null);
  sesion = null; P.ls.set("sesion", null);
  sucio = false; version = 0; bloqueado = false; aviso = ""; error = "";
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
  if (!r.ok) {
    ocupado = false;
    btn.disabled = false; btn.textContent = crear ? "Crear cuenta" : "Entrar";
    return fallo(MENSAJES[r.error] || "No se ha podido completar. Vuelve a intentarlo.");
  }
  btn.textContent = "Preparando el cifrado…";
  empezarSesion({ token: r.token, nombre: r.nombre, clave: await derivarClave(r.nombre, pass) }, crear);
  // si se han pasado votos de este navegador a la cuenta, se enseña el aviso
  ocupado = false;
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
  sesion = null; P.ls.set("sesion", null); sucio = false; version = 0;
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
const PRIVACIDAD = `<p class="fine">Tus votos se cifran en tu navegador con una clave que sale de tu contraseña y nunca se envía. La base de datos (Supabase) solo guarda datos ilegibles: ni quien administra esta web puede ver qué has votado. Por eso, si olvidas la contraseña, tus votos guardados no se pueden recuperar.</p>`;

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
// Si la base de datos aún no tiene las funciones (migraciones sin aplicar),
// la web funciona sin cuentas en vez de enseñar un registro que fallaría.
(async () => {
  const prueba = await rpc("papeleta_leer", { p_token: "comprobar" });
  if (prueba.error === "NO_INSTALADO") {
    P.usarCuenta(null);
    P.nota("Tus votos se guardan solo en este navegador.");
    return;
  }
  P.activarCuentas(render);
  if (sesion && !sesion.clave) {
    // sesión de antes del cifrado: hace falta la contraseña para sacar la clave
    caducada();
    error = "Ahora tus votos se guardan cifrados. Vuelve a entrar con tu contraseña para activarlo.";
    render();
  } else if (sesion) {
    P.usarCuenta(sesion.nombre);
    P.cuentaTexto(sesion.nombre);
    setEstado("");
    cargar();
  } else {
    P.usarCuenta(null);
    setEstado("");
    if (!P.ls.get("sinCuenta", false)) P.mostrar("cuenta");
  }
})();
