"""Prueba el deslizamiento de tarjetas con toques reales (no ratón).

Abre docs/index.html en Chrome en modo móvil (pantalla táctil) y manda
eventos táctiles por CDP, así que el navegador aplica sus reglas de scroll
y touch-action igual que en un teléfono. Comprueba:
  1. deslizar a la derecha vota «A favor» y revela el partido;
  2. deslizar de nuevo pasa a la siguiente tarjeta;
  3. deslizar a la izquierda vota «En contra»;
  4. arrastrar en vertical sigue haciendo scroll del texto (y no vota).

Uso: .venv/bin/python scripts/test_tactil.py
"""
import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parent.parent / "docs"


def servidor():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DOCS))
    h.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def arrastrar(cdp, x0, y0, x1, y1, pasos=12):
    pt = lambda x, y: [{"x": x, "y": y, "id": 1}]
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": pt(x0, y0)})
    for i in range(1, pasos + 1):
        x = x0 + (x1 - x0) * i / pasos
        y = y0 + (y1 - y0) * i / pasos
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": pt(x, y)})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def main():
    srv = servidor()
    url = f"http://127.0.0.1:{srv.server_address[1]}/#tarjetas"
    fallos = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True,
                            device_scale_factor=3)
        # sin cuentas ni servidor: solo interesa el gesto
        ctx.route("**/rest/v1/**", lambda r: r.abort())
        ctx.add_init_script("try { localStorage.setItem('p29n.sinCuenta', 'true') } catch (e) {}")
        pg = ctx.new_page()
        pg.goto(url)
        pg.wait_for_selector(".card .card-text")
        cdp = ctx.new_cdp_session(pg)

        def caja():
            return pg.eval_on_selector(".card", "e => { const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2] }")

        def estado():
            return pg.evaluate("""() => ({
                revelada: !!document.querySelector('.card.revealed'),
                progreso: document.getElementById('prog-text').textContent,
                scroll: document.querySelector('.card .card-body').scrollTop,
                pulsado: [...document.querySelectorAll('#vote-bar .vbtn')].findIndex(b => b.getAttribute('aria-pressed') === 'true'),
            })""")

        def comprobar(nombre, cond, info):
            print(("OK   " if cond else "FALLO") + f" {nombre}: {info}")
            if not cond:
                fallos.append(nombre)

        # 4) vertical: hace scroll y no vota (usar una tarjeta con texto largo)
        for _ in range(30):
            alto = pg.eval_on_selector(".card .card-body", "e => e.scrollHeight - e.clientHeight")
            if alto > 120:
                break
            pg.click("#btn-skip")
            pg.wait_for_timeout(350)
        x, y = caja()
        arrastrar(cdp, x, y + 150, x + 5, y - 150)
        pg.wait_for_timeout(400)
        e = estado()
        comprobar("vertical hace scroll y no vota", e["scroll"] > 0 and not e["revelada"], e)

        # 1) derecha -> A favor
        x, y = caja()
        arrastrar(cdp, x - 60, y, x + 140, y + 10)
        pg.wait_for_timeout(500)
        e = estado()
        comprobar("derecha vota A favor", e["revelada"] and e["pulsado"] == 3, e)

        # 2) deslizar otra vez -> siguiente tarjeta
        x, y = caja()
        arrastrar(cdp, x - 60, y, x + 140, y)
        pg.wait_for_timeout(600)
        e = estado()
        comprobar("deslizar tras votar pasa a la siguiente", not e["revelada"], e)

        # 3) izquierda -> En contra
        x, y = caja()
        arrastrar(cdp, x + 60, y, x - 140, y - 10)
        pg.wait_for_timeout(500)
        e = estado()
        comprobar("izquierda vota En contra", e["revelada"] and e["pulsado"] == 1, e)

        b.close()
    srv.shutdown()
    print("\n" + ("Todo bien" if not fallos else f"{len(fallos)} fallo(s)"))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
