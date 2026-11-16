"""Extrae las medidas del programa de Vox (29N 2026) de forma literal.

Fuente: https://www.voxespana.es/wp-content/uploads/2026/11/Programa-completo-A5-1.pdf
«Programa electoral. Es sentido común», 66 págs. A5.

Maquetación (por tipografía):
  - Gotham-Medium 10 «N.» en x < 75     -> número de medida
  - Gotham-Medium (negrita) / Gotham-Light, x >= 75 -> texto de la medida
  - Gotham-Bold «•» en x ≈ 79           -> viñeta dentro de la medida
  - GothamCondensed 22 verde            -> bloque temático (INMIGRACIÓN, …)
  - Gotham-Bold 10 blanco abajo         -> número de página impreso
  - «ES SENTIDO COMÚN» blanco arriba    -> cabecera (se ignora)
Los cortes de palabra usan guion blando (U+00AD), que se elimina.

Uso: .venv/bin/python scripts/extraer_vox.py
"""
import re

import pymupdf

from comun import ROOT, Texto, con_huecos, guardar, lineas, spans

PDF = ROOT / "fuentes/vox/Programa-completo-A5-1.pdf"
URL = "https://www.voxespana.es/wp-content/uploads/2026/11/Programa-completo-A5-1.pdf"
GREEN = 0x246848


def rol(s):
    f, sz, c, t = s["font"], s["size"], s["color"], s["text"].strip()
    if f.startswith("GothamCondensed") and abs(sz - 22) < .5 and c == GREEN:
        return "bloque"
    if c == 0xFFFFFF:
        return "pagina" if f == "Gotham-Bold" and t.isdigit() and s["y"] > 540 else None
    if f == "Gotham-Medium" and abs(sz - 10) < .3 and s["x"] < 75 and re.fullmatch(r"\d+\.", t):
        return "num"
    if f == "Gotham-Bold" and t == "•":
        return "vineta"
    if f in ("Gotham-Medium", "Gotham-Light", "Gotham-Book", "Gotham-Bold") and 9.5 < sz < 10.3:
        return "cuerpo"
    return None


def main():
    doc = pymupdf.open(PDF)
    medidas = []
    cur = None
    bloque = ""
    prev_bloque_y = None

    def cerrar():
        nonlocal cur
        if cur is not None:
            cur["titulo"] = ""
            cur["texto"] = cur.pop("_t").marcado()
            medidas.append(cur)
            cur = None

    for page in doc:
        pdf_p = page.number + 1
        sp = []
        for s in spans(page):
            # a veces el número y el texto vienen juntos: «100.\tIndependencia…»
            m = re.match(r"(\d+\.)\s+(\S.*)$", s["text"], re.S)
            if m and s["font"] == "Gotham-Medium" and s["x"] < 75:
                sp.append(dict(s, text=m.group(1)))
                sp.append(dict(s, text=m.group(2), x=s["x"] + 25))
            else:
                sp.append(s)
        impresa = next((int(s["text"].strip()) for s in sp if rol(s) == "pagina"), pdf_p)
        last_y = None
        prev_bloque_y = None
        for ln in lineas([s for s in sp if rol(s) not in (None, "pagina")]):
            roles = [rol(s) for s in ln]
            if roles[0] == "bloque":
                cerrar()
                txt = " ".join(s["text"].strip() for s in ln)
                bloque = f"{bloque} {txt}" if prev_bloque_y is not None and ln[0]["y"] - prev_bloque_y < 40 else txt
                prev_bloque_y = ln[0]["y"]
                continue
            if "num" in roles:
                cerrar()
                num = next(s for s in ln if rol(s) == "num")
                cur = {
                    "n": int(num["text"].strip().rstrip(".")),
                    "pagina": impresa, "pagina_fin": impresa,
                    "pagina_pdf": pdf_p, "pagina_pdf_fin": pdf_p,
                    "bloque": bloque.strip().capitalize() if bloque.isupper() else bloque.strip(),
                    "bloque_original": bloque.strip(),
                    "_t": Texto(guion_real=True),
                }
                ln = [s for s in ln if rol(s) != "num"]
                last_y = None
                if not ln:
                    continue
            if cur is None:
                continue
            t = cur["_t"]
            y = ln[0]["y"]
            if rol(ln[0]) == "vineta":
                t.salto(vineta=True)
                ln = ln[1:]
            elif last_y is not None and y - last_y > 22 and min(s["x"] for s in ln) < 90:
                t.salto()
            else:
                t.nueva_linea()
            for s, hueco in con_huecos(ln):
                if rol(s) == "cuerpo":
                    t.add(s["text"], s["font"] in ("Gotham-Medium", "Gotham-Bold"), hueco)
            last_y = y
            cur["pagina_fin"] = impresa
            cur["pagina_pdf_fin"] = pdf_p
    cerrar()

    for m in medidas:
        m["apartado_titulo"] = m.pop("bloque_original") or None
        m["bloque"] = None
    guardar("vox", "Vox", "Programa electoral. Es sentido común. Elecciones generales 29 de noviembre de 2026",
            URL, medidas, unidad="Medida")


if __name__ == "__main__":
    main()
