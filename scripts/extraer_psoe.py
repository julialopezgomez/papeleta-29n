"""Extrae los compromisos del programa del PSOE (29N 2026) de forma literal.

Fuente: https://www.psoe.es/media-content/2026/11/PROGRAMAPSOE29N26.pdf
«La fuerza de seguir avanzando», 114 págs.

Maquetación (por tipografía):
  - Geomanist-Bold 11 rojo «N.»      -> número de compromiso
  - Arial/Segoe 11 negro, x >= 104    -> texto del compromiso (negrita = Bold)
  - CourierNew «o» / Times «●»        -> viñeta dentro del compromiso
  - Geomanist-Medium 22 rojo          -> capítulo
  - Geomanist-Regular 18 rojo         -> apartado
  - Arial-Italic 13.9 rojo            -> subapartado
  - Geomanist-Regular 12 rojo abajo   -> número de página impreso
  - Arial 11 negro en x ≈ 72          -> texto introductorio (no es compromiso)

Uso: .venv/bin/python scripts/extraer_psoe.py
"""
import re

import pymupdf

from comun import ROOT, Texto, con_huecos, guardar, lineas, spans

PDF = ROOT / "fuentes/psoe/PROGRAMAPSOE29N26.pdf"
URL = "https://www.psoe.es/media-content/2026/11/PROGRAMAPSOE29N26.pdf"
RED = 0xEE0000


def rol(s):
    f, sz, c = s["font"], s["size"], s["color"]
    if f.startswith("Geomanist-Bold") and abs(sz - 11) < .3 and c == RED and re.fullmatch(r"\d+\.", s["text"].strip()):
        return "num"
    if f.startswith("Geomanist-Medium") and sz > 20 and c == RED:
        return "capitulo"
    if f.startswith("Geomanist-Regular") and abs(sz - 18) < .5 and c == RED:
        return "apartado"
    if f.startswith("Arial-Italic") and sz > 13 and c == RED:
        return "sub"
    if f.startswith("Geomanist-Regular") and abs(sz - 12) < .3 and c == RED and s["y"] > 740:
        return "pagina"
    if c == 0 and 10.3 < sz < 11.3 and (f.startswith(("Arial", "SegoeUI", "TimesNewRoman", "CourierNew"))):
        if f.startswith("CourierNew") and s["text"].strip() == "o" or f.startswith("TimesNewRoman") and s["text"].strip() == "●":
            return "vineta"
        return "cuerpo"
    if f.startswith("Geomanist-Medium") and 10.5 < sz < 11.5:
        return "compromisos"
    return None


def main():
    doc = pymupdf.open(PDF)
    medidas = []
    cur = None
    titulos = {"capitulo": "", "apartado": "", "sub": ""}
    ultimo_rol_titulo = None

    def cerrar():
        nonlocal cur
        if cur is not None:
            t = cur.pop("_t")
            cur["titulo"] = ""
            cur["texto"] = t.marcado()
            medidas.append(cur)
            cur = None

    for page in doc:
        pdf_p = page.number + 1
        sp = spans(page)
        impresa = next((int(s["text"].strip()) for s in sp if rol(s) == "pagina" and s["text"].strip().isdigit()), None)
        last_y = None
        for ln in lineas([s for s in sp if rol(s) not in (None, "pagina")]):
            roles = [rol(s) for s in ln]
            r0 = roles[0]
            # títulos (pueden ocupar varias líneas seguidas)
            if r0 in ("capitulo", "apartado", "sub"):
                cerrar()
                txt = "".join(s["text"] for s in ln).strip()
                if ultimo_rol_titulo == r0:
                    titulos[r0] = (titulos[r0] + " " + txt).strip()
                else:
                    titulos[r0] = txt
                    if r0 == "capitulo":
                        titulos["apartado"] = titulos["sub"] = ""
                    elif r0 == "apartado":
                        titulos["sub"] = ""
                ultimo_rol_titulo = r0
                continue
            ultimo_rol_titulo = None
            if r0 == "compromisos":
                cerrar()
                continue
            if "num" in roles:
                cerrar()
                num = next(s for s in ln if rol(s) == "num")
                cur = {
                    "n": int(num["text"].strip().rstrip(".")),
                    "pagina": impresa, "pagina_fin": impresa,
                    "pagina_pdf": pdf_p, "pagina_pdf_fin": pdf_p,
                    "bloque": titulos["capitulo"], "apartado_titulo": titulos["apartado"],
                    "contexto": titulos["sub"], "_t": Texto(guion_real=True),
                }
                ln = [s for s in ln if rol(s) != "num"]
                last_y = None
                if not ln:
                    continue
            if cur is None:
                continue
            x0 = min(s["x"] for s in ln)
            if x0 < 100:  # texto introductorio a la izquierda: termina el compromiso
                cerrar()
                continue
            y = ln[0]["y"]
            t = cur["_t"]
            if roles[0] == "vineta" or (len(ln) > 1 and rol(ln[0]) == "vineta"):
                t.salto(vineta=True)
                ln = ln[1:]
            elif last_y is not None and y - last_y > 28:
                t.salto()
            else:
                t.nueva_linea()
            for s, hueco in con_huecos(ln):
                if rol(s) == "cuerpo":
                    t.add(s["text"], s["bold"], hueco)
            last_y = y
            cur["pagina_fin"] = impresa
            cur["pagina_pdf_fin"] = pdf_p
    cerrar()

    for m in medidas:
        for k in ("bloque", "apartado_titulo", "contexto"):
            m[k] = re.sub(r"\s+", " ", m[k] or "").strip() or None
    guardar("psoe", "PSOE", "La fuerza de seguir avanzando. Programa electoral elecciones generales 2026",
            URL, medidas, unidad="Compromiso")


if __name__ == "__main__":
    main()
