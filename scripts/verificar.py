"""Comprueba que cada medida extraída es literal respecto al PDF.

Para cada medida, trocea título y texto en frases y verifica que cada frase
aparece tal cual en el texto de las páginas indicadas (normalizando solo
espacios y guiones de partición de palabra al final de línea).

Uso:  .venv/bin/python scripts/verificar.py data/pp.json fuentes/pp/X.pdf
"""
import json
import re
import sys

import pymupdf


def norm(s):
    s = s.replace("\u2018\u2018", "")  # comillas decorativas de las citas
    s = re.sub(r"(\d)-\s*\n\s*(\d)", r"\1-\2", s)  # 2028-\n2034
    s = re.sub(r"([^\W\d])-\s*\n\s*(\w)", r"\1\2", s)  # guion de partición
    s = re.sub(r"\s+", " ", s)
    return s.replace("­", "").strip()


def texto_pagina(page):
    """Texto de la página sin el número de página impreso (cabecera/pie)."""
    h = page.rect.height
    out = []
    for b in page.get_text("blocks"):
        x0, y0, x1, y1, txt = b[:5]
        if (y1 < 60 or y0 > h - 40) and txt.strip().isdigit():
            continue
        out.append(txt)
    return "\n".join(out)


def squash(s):
    # sin espacios: tolera saltos de línea/columnas en mitad de frases
    return re.sub(r"\s+", "", s)


def main(json_path, pdf_path):
    data = json.load(open(json_path))
    doc = pymupdf.open(pdf_path)
    page_text = [texto_pagina(p) for p in doc]
    # desfase entre página impresa y página del PDF
    fallos = 0
    total = 0
    for m in data["medidas"]:
        if m.get("pendiente"):
            continue
        a = m.get("pagina_pdf", m["pagina"]) - 1
        b = a + (m["pagina_fin"] - m["pagina"])
        hay = squash(norm("\n".join(page_text[max(0, a - 1): b + 2])))
        frases = [m["titulo"]] + re.split(r"(?<=[.:;])\s+", m["texto"].replace("\n\n", " "))
        for f in frases:
            f = f.strip()
            if len(f) < 4:
                continue
            total += 1
            if squash(f) not in hay:
                fallos += 1
                print(f"[{m['n']}] NO ENCONTRADA: {f[:120]}")
    print(f"{total - fallos}/{total} frases verificadas literalmente")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
