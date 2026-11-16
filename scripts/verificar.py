"""Comprueba que cada medida extraída es literal respecto al PDF.

Para cada medida, trocea título y texto en frases y verifica que cada frase
aparece tal cual en el texto de las páginas indicadas (normalizando solo
saltos de línea y guiones de partición de palabra al final de línea).

Uso:  .venv/bin/python scripts/verificar.py data/pp.json fuentes/pp/X.pdf
      .venv/bin/python scripts/verificar.py --todos
"""
import json
import re
import sys

import pymupdf


def norm(s, partir=True):
    """partir=True: un «-» a final de línea se toma como corte de palabra;
    partir=False: se conserva como guion de verdad (público-\\nprivada)."""
    s = s.replace("\u2018\u2018", "")  # comillas decorativas de las citas
    s = re.sub("\u00ad\\s*", "", s)  # guion blando (corte de palabra)
    s = re.sub(r"(\d)-\s*\n\s*(\d)", r"\1-\2", s)  # 2028-\n2034
    if partir:
        s = re.sub(r"([^\W\d])-\s*\n\s*(\w)", r"\1\2", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def texto_bloques(page):
    """Texto de la página por bloques, sin cabecera ni pie."""
    h = page.rect.height
    return "\n".join(b[4] for b in page.get_text("blocks")
                     if not (b[3] < 0.08 * h or b[1] > 0.92 * h))


def texto_pagina(page):
    """Texto de la página línea a línea, sin cabecera ni pie (franjas del 8 %
    superior e inferior), sin números sueltos (páginas, círculos decorativos)
    y sin los símbolos de viñeta."""
    h = page.rect.height
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            partes = []
            for s in l["spans"]:
                y0 = s["bbox"][1]
                t = s["text"]
                if y0 < 0.08 * h or y0 > 0.92 * h or t.strip().isdigit():
                    continue
                partes.append(t)
            if partes:
                out.append("".join(partes))
    return re.sub(r"[●▶▷•]", " ", "\n".join(out))


def squash(s):
    # espacios normalizados a uno solo: las palabras tienen que coincidir
    # exactamente, incluidos los espacios entre ellas
    return re.sub(r"\s+", " ", s).strip()


def main(json_path, pdf_path):
    data = json.load(open(json_path))
    doc = pymupdf.open(pdf_path)
    # dos lecturas del PDF (por líneas y por bloques): cada frase tiene que
    # aparecer literal y seguida en al menos una de ellas
    lecturas = ([texto_pagina(p) for p in doc], [texto_bloques(p) for p in doc])
    # desfase entre página impresa y página del PDF
    fallos = 0
    total = 0
    for m in data["medidas"]:
        if m.get("pendiente"):
            continue
        a = m.get("pagina_pdf", m["pagina"]) - 1
        b = m["pagina_pdf_fin"] - 1 if "pagina_pdf_fin" in m else a + (m["pagina_fin"] - m["pagina"])
        hays = []
        for page_text in lecturas:
            bruto = "\n".join(page_text[max(0, a - 1): b + 2])
            hays += [squash(norm(bruto)), squash(norm(bruto, partir=False))]
        # el texto guardado marca la negrita con ** y las viñetas internas con «• »
        texto = re.sub(r"(^|\n)• ", r"\1", m["texto"].replace("**", ""))
        frases = [m["titulo"]] + re.split(r"(?<=[.:;])\s+|\n", texto)
        for f in frases:
            f = f.strip()
            if len(f) < 4:
                continue
            total += 1
            if not any(squash(f) in h for h in hays):
                fallos += 1
                print(f"[{m['n']}] NO ENCONTRADA: {f[:120]}")
    print(f"{total - fallos}/{total} frases verificadas literalmente")
    return 1 if fallos else 0


PROGRAMAS = {
    "pp": "fuentes/pp/LA-RECONSTRUCCION-NACIONAL.pdf",
    "psoe": "fuentes/psoe/PROGRAMAPSOE29N26.pdf",
    "vox": "fuentes/vox/Programa-completo-A5-1.pdf",
    "fa": "fuentes/fa/ProgramaFrenteAmplio.pdf",
}

if __name__ == "__main__":
    if sys.argv[1:] == ["--todos"]:
        r = 0
        for p, pdf in PROGRAMAS.items():
            print(f"== {p}")
            r |= main(f"data/{p}.json", pdf)
        sys.exit(r)
    sys.exit(main(sys.argv[1], sys.argv[2]))
