"""Extrae las medidas del programa de Frente Amplio (29N 2026) de forma literal.

Fuente: https://frenteamplio.info/pdf/ProgramaFrenteAmplio.pdf (151 págs.)

Frente Amplio NO numera sus medidas: son viñetas (●) agrupadas bajo
subtítulos dentro de apartados numerados (1.1., 1.2., …). Cada viñeta es una
medida y se referencia como «apartado 1.1 · punto 3» (orden dentro del
apartado) más la página impresa. `n` es solo un identificador interno.

Maquetación (por tipografía):
  - Inter 5.2 rojo «●»                 -> nueva medida
  - Inter 5.8 rojo «▶»                 -> viñeta dentro de la medida
  - Inter 10 gris oscuro, x >= 118     -> texto de la medida
  - MarrSans-Medium 15 rojo «1.1.»     -> apartado
  - MarrSans-Medium 12 rojo            -> subtítulo (grupo de medidas)
  - MarrSansCond-Semibold 9 rojo arriba (solo cifras) -> página impresa
  - Inter 10 en x ≈ 85                 -> texto introductorio (no es medida)
Los cortes de palabra usan guion blando (U+00AD), que se elimina.

Uso: .venv/bin/python scripts/extraer_fa.py
"""
import re

import pymupdf

from comun import ROOT, Texto, con_huecos, guardar, lineas, spans

PDF = ROOT / "fuentes/fa/ProgramaFrenteAmplio.pdf"
URL = "https://frenteamplio.info/pdf/ProgramaFrenteAmplio.pdf"
RED = 0xF03C12

CAPITULOS = {
    1: "Acabar con la especulación y garantizar el derecho a la vivienda",
    2: "Derechos sociales para una vida digna",
    3: "Una reforma fiscal en profundidad",
    4: "Salarios y pensiones dignos y precios asequibles",
    5: "Continuar el impulso hacia una transición ecológica justa",
    6: "Estado emprendedor y política industrial activa",
    7: "Agricultura, ganadería y pesca: hacia su sostenibilidad medioambiental, social y económica",
    8: "Autónomos, pymes y economía social",
    9: "Lucha contra la despoblación y retos de la insularidad",
    10: "Empleo público de calidad",
    11: "Financiación autonómica y vertebración territorial",
    12: "Ayuntamientos con recursos y autonomía",
    13: "Democratización económica y poder financiero",
    14: "Poder digital y pluralismo informativo",
    15: "Igualdad y más derechos para todas, todos y todes",
    16: "Migraciones y antirracismo",
    17: "La seguridad humana: paz, solidaridad y Europa",
    18: "Hacia una democracia avanzada",
}


def rol(s):
    f, sz, c, t = s["font"], s["size"], s["color"], s["text"].strip()
    if f.startswith("Inter") and c == RED and sz < 6:
        return "vineta" if t == "●" else "subvineta" if t in ("▶", "▷") else None
    if f.startswith("MarrSansCond-Semibold") and abs(sz - 9) < .3 and s["y"] < 80:
        return "pagina" if t.isdigit() else None
    if f.startswith("MarrSans-Medium") and abs(sz - 15) < .5 and c == RED:
        return "apartado"
    if f.startswith("MarrSans-Medium") and abs(sz - 12) < .5 and c == RED:
        return "subtitulo"
    if f.startswith("Inter") and abs(sz - 10) < .3 and c != RED:
        return "cuerpo"
    return None


def paginas_impresas(doc):
    """Página impresa de cada página del PDF (las que no la llevan se deducen)."""
    nums = []
    for page in doc:
        sp = spans(page, y_max=80)
        nums.append(next((int(s["text"].strip()) for s in sp if rol(s) == "pagina"), None))
    for i in range(len(nums)):
        if nums[i] is None:
            nxt = next(((j, nums[j]) for j in range(i + 1, len(nums)) if nums[j] is not None), None)
            prv = next(((j, nums[j]) for j in range(i - 1, -1, -1) if nums[j] is not None), None)
            if nxt and (not prv or nxt[1] - prv[1] != nxt[0] - prv[0] or True):
                nums[i] = nxt[1] - (nxt[0] - i)
            elif prv:
                nums[i] = prv[1] + (i - prv[0])
    return nums


def main():
    doc = pymupdf.open(PDF)
    impresas = paginas_impresas(doc)
    medidas = []
    sueltos = []  # texto con sangría de medida pero sin viñeta (para revisar)
    cur = None
    apartado, apartado_titulo, subtitulo = None, "", ""
    ult_titulo = None  # rol del último título leído (para títulos de varias líneas)
    puntos = {}

    def cerrar():
        nonlocal cur
        if cur is not None:
            t = cur.pop("_t")
            cur["titulo"] = ""
            cur["texto"] = t.marcado()
            if cur["texto"]:
                medidas.append(cur)
            cur = None

    for page in doc:
        pdf_p = page.number + 1
        impresa = impresas[page.number]
        last_y = None
        for ln in lineas([s for s in spans(page) if rol(s) not in (None, "pagina")]):
            roles = [rol(s) for s in ln]
            r0 = roles[0]
            txt = "".join(s["text"] for s in ln)
            if r0 == "apartado":
                cerrar()
                m = re.match(r"\s*(\d+\.\d+)\.\s*(.*)$", txt, re.S)
                if m:
                    apartado, apartado_titulo = m.group(1), m.group(2).strip()
                elif ult_titulo == "apartado":
                    apartado_titulo += " " + txt.strip()
                subtitulo = ""
                ult_titulo = "apartado"
                continue
            if r0 == "subtitulo":
                cerrar()
                subtitulo = (subtitulo + " " + txt.strip()) if ult_titulo == "subtitulo" else txt.strip()
                ult_titulo = "subtitulo"
                continue
            ult_titulo = None
            if r0 == "vineta":
                cerrar()
                puntos[apartado] = puntos.get(apartado, 0) + 1
                cur = {
                    "n": len(medidas) + 1,
                    "ref": f"Apartado {apartado} · punto {puntos[apartado]}" if apartado else None,
                    "apartado": apartado,
                    "pagina": impresa, "pagina_fin": impresa,
                    "pagina_pdf": pdf_p, "pagina_pdf_fin": pdf_p,
                    "bloque": CAPITULOS.get(int(apartado.split(".")[0])) if apartado else None,
                    "apartado_titulo": re.sub(r"\s+", " ", apartado_titulo).strip() or None,
                    "contexto": re.sub(r"\s+", " ", subtitulo).strip() or None,
                    "_t": Texto(guion_real=True),
                }
                ln = ln[1:]
                last_y = None
                if not ln:
                    continue
            x0 = min(s["x"] for s in ln)
            if cur is None or x0 < 110:
                if x0 >= 110 and r0 == "cuerpo":
                    sueltos.append((impresa, txt.strip()))
                if x0 < 110:
                    cerrar()
                continue
            t = cur["_t"]
            y = ln[0]["y"]
            if rol(ln[0]) == "subvineta":
                t.salto(vineta=True)
                ln = ln[1:]
            elif last_y is not None and y - last_y > 18:
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

    # renumerar n en orden y avisar de texto sin viñeta
    for i, m in enumerate(medidas, 1):
        m["n"] = i
    (ROOT / "data/fa_sin_vineta.txt").write_text("\n".join(f"p{p}: {t}" for p, t in sueltos))
    if sueltos:
        print(f"  {len(sueltos)} líneas sangradas sin viñeta -> data/fa_sin_vineta.txt")
    guardar("fa", "Frente Amplio", "Programa electoral Frente Amplio. Elecciones generales 2026",
            URL, medidas, unidad="Punto", numeradas=False)


if __name__ == "__main__":
    main()
