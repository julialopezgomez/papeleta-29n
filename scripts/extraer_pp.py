"""Extrae las medidas del programa del PP (29N 2026) de forma literal.

Fuente: https://www.pp.es/wp-content/uploads/2026/11/LA-RECONSTRUCCION-NACIONAL.pdf

El PDF usa tipografías distintas para cada elemento, así que se identifica cada
parte por su fuente:
  - Anth-Bold 18, color #4dc1df  -> número de medida
  - Montserrat-Bold 11            -> título de la medida (en mayúsculas)
  - Montserrat-Light/Regular 11   -> cuerpo de la medida
  - Anth-BoldItalic 19 "1.1"      -> apartado
  - Montserrat-Regular 15 blanco  -> aviso "Permanezca atento a la campaña…"
El resto (citas laterales, portadillas, decoración) se descarta.

Uso:  .venv/bin/python scripts/extraer_pp.py
Salida: data/pp.json
"""
import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "fuentes/pp/LA-RECONSTRUCCION-NACIONAL.pdf"
OUT = ROOT / "data/pp.json"
URL = "https://www.pp.es/wp-content/uploads/2026/11/LA-RECONSTRUCCION-NACIONAL.pdf"

BLOQUES = {
    "1": "Reparar el Estado",
    "2": "Regenerar la democracia",
    "3": "Reunir a la Nación",
    "4": "Recuperar la ambición y la autoestima",
}

# Títulos de apartado tal y como aparecen en el índice (pág. 7)
APARTADOS = {
    "1.1": "La Administración será rigurosa, dimensionada y eficaz",
    "1.2": "El Estado dejará de asfixiar al que cumple y de subvencionar al que se aprovecha",
    "1.3": "El Estado estará presente en toda España",
    "1.4": "Se hará cumplir la ley en todo el territorio",
    "1.5": "Nuestro país recuperará el control de sus fronteras",
    "1.6": "Vivir en España será un compromiso mutuo",
    "1.7": "El Gobierno llegará el primero cuando haya una emergencia",
    "1.8": "España tendrá medios para su defensa",
    "2.1": "El poder se ganará con más garantías y se ejercerá de forma más estable",
    "2.2": "Nadie gobernará sin presupuestos ni gastará sin control",
    "2.3": "El poder no controlará a quien lo vigila",
    "2.4": "La política nunca será un negocio",
    "2.5": "El Parlamento volverá a hacer buenas leyes y a controlar al Gobierno",
    "3.1": "Una ciudadanía común",
    "3.2": "Unir territorios, generaciones y personas",
    "3.3": "Unas infraestructuras seguras que vertebren España",
    "3.4": "Recuperar lo que compartimos",
    "3.5": "La nacionalidad es un vínculo de pertenencia",
    "4.1": "Se construirá un millón de viviendas más en España",
    "4.2": "España será el mejor país de Europa para formar una familia",
    "4.3": "En España siempre merecerá la pena trabajar, emprender y arriesgar",
    "4.4": "Los españoles pagarán menos impuestos",
    "4.5": "España cerrará la brecha de productividad con Europa",
    "4.6": "El mundo rural volverá a ser atractivo y rentable",
    "4.7": "España tendrá su mejor resultado en PISA en cuatro años",
    "4.8": "Seremos referente mundial en sanidad y cuidados",
    "4.9": "España puede ser potencia energética de Europa",
    "4.10": "Recuperaremos el lugar que nos corresponde en el mundo",
}

PENDIENTE = "Permanezca atento a la campaña para conocer esta nueva medida"

TEAL = 0x4DC1DF
DARK = 0x135898


def role(span):
    f, sz, c = span["font"], round(span["size"]), span["color"]
    if f == "Anth-Bold" and sz == 18 and c == TEAL:
        return "num"
    if f == "Anth-BoldItalic" and sz == 19 and c == TEAL:
        return "sec_num"
    if f == "Anth-Italic" and sz == 19 and c == DARK:
        return "sec_or_pull"
    if f == "Anth-Regular" and sz in (25, 60):
        return "block"
    if f == "Montserrat-Bold" and sz == 11 and c == DARK:
        return "title"
    if f in ("Montserrat-Light", "Montserrat-Regular") and sz == 11 and c == DARK:
        return "body"
    return None


def page_lines(page):
    """Devuelve (líneas, pulls) del texto principal en orden de lectura.

    Cada línea es una lista de [role, text, x, y, y1]. `pulls` son los
    titulares laterales en cursiva (no forman parte de ninguna medida)."""
    spans = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                if not s["text"].strip():
                    continue
                r = role(s)
                x, y = s["bbox"][0], s["bbox"][1]
                if r is None or y < 60:  # y<60: número de página impreso
                    continue
                spans.append([r, s["text"], x, y, s["bbox"][3]])
    # Las cursivas grandes solo son título de apartado si están junto a "1.1"
    secs = [s for s in spans if s[0] == "sec_num"]
    pulls = []
    kept = []
    for s in spans:
        if s[0] == "sec_or_pull":
            if any(-3 < s[3] - h[3] < 45 and s[2] >= h[2] - 3 for h in secs):
                kept.append(s)
            else:
                pulls.append(s)
        else:
            kept.append(s)
    # agrupar por línea (tolerancia vertical de 4 pt)
    kept.sort(key=lambda s: (s[3], s[2]))
    lines = []
    for s in kept:
        if lines and abs(lines[-1][0][3] - s[3]) < 4 and s[0] != "num" and lines[-1][0][0] != "num":
            lines[-1].append(s)
        else:
            lines.append([s])
    for ln in lines:
        ln.sort(key=lambda s: s[2])
    return lines, pulls


def printed_page_number(page):
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                if s["bbox"][1] < 60 and s["text"].strip().isdigit():
                    return int(s["text"].strip())
    return None


def join_lines(parts):
    """Une líneas de texto respetando guiones de partición de palabra."""
    out = ""
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip()
        if not p:
            continue
        if not out:
            out = p
            continue
        if out == "\n\n" or out.endswith("\n\n"):
            out += p
            continue
        m = re.search(r"(\w+)-$", out)
        if m and m.group(1)[-1].isdigit() and p[0].isdigit():
            out += p  # "2028-" + "2034" -> "2028-2034"
        elif m and p[0].isalpha():
            prev = m.group(1)
            # "Castilla-" + "La Mancha": guion real si la palabra previa no está
            # en mayúsculas y la siguiente empieza por mayúscula.
            if p[0].isupper() and not prev.isupper():
                out += p
            else:
                out = out[:-1] + p
        else:
            out += " " + p
    return out


def main():
    doc = pymupdf.open(PDF)
    medidas = []
    descartado = []  # texto de introducción que NO pertenece a ninguna medida
    cur = None
    seccion = None
    intro = True  # estamos en texto introductorio (no medida)

    def close():
        nonlocal cur
        if cur is None:
            return
        cur["titulo"] = join_lines(cur.pop("_title")).strip()
        cur["texto"] = join_lines(cur.pop("_body")).strip()
        # el punto final del título a veces está en la fuente del cuerpo
        if cur["texto"] and cur["texto"][0] in ".:":
            cur["titulo"] += cur["texto"][0]
            cur["texto"] = cur["texto"][1:].strip()
        medidas.append(cur)
        cur = None

    for pi, page in enumerate(doc):
        pdf_page = pi + 1
        printed = printed_page_number(page) or pdf_page
        lines, pulls = page_lines(page)
        last_y = None
        for ln in lines:
            r0 = ln[0][0]
            y = ln[0][3]
            roles = {s[0] for s in ln}

            if r0 == "num":
                txt = ln[0][1].strip()
                if not txt.isdigit():
                    continue
                close()
                intro = False
                cur = {
                    "n": int(txt),
                    "pagina": printed,
                    "pagina_fin": printed,
                    "pagina_pdf": pdf_page,
                    "apartado": seccion,
                    "_title": [],
                    "_body": [],
                }
                last_y = None
                continue

            if "sec_num" in roles:
                close()
                seccion = [s for s in ln if s[0] == "sec_num"][0][1].strip()
                intro = True
                continue

            if r0 in ("block", "sec_or_pull"):
                if r0 == "block":
                    close()
                    intro = True
                continue

            if not (roles & {"title", "body"}):
                continue

            if cur is not None and not intro and (cur["_body"] or cur["_title"]):
                # un salto vertical grande dentro de la página = fin de la medida
                gap_end = last_y is not None and y - last_y > 22
                # al empezar página: si hay un titular lateral junto a la
                # primera línea y la medida ya terminó en punto -> intro
                top_intro = (
                    last_y is None
                    and cur["_body"]
                    and cur["_body"][-1].rstrip().endswith(".")
                    and any(abs(p[3] - y) < 60 for p in pulls)
                )
                if gap_end or top_intro:
                    close()
                    intro = True

            txt_line = "".join(s[1] for s in ln)
            if cur is None or intro:
                descartado.append((printed, txt_line))
                last_y = y
                continue

            title_txt = "".join(s[1] for s in ln if s[0] == "title")
            body_txt = "".join(s[1] for s in ln if s[0] == "body")
            if title_txt:
                cur["_title"].append(title_txt)
            if body_txt:
                cur["_body"].append(body_txt)
            cur["pagina_fin"] = printed
            last_y = y
    close()

    Path(ROOT / "data/pp_descartado.txt").write_text(
        "\n".join(f"p{p}: {t}" for p, t in descartado)
    )

    # normalizar apartados y marcar medidas reservadas para campaña
    final = []
    for m in medidas:
        pend = m.pop("_pending", None)
        sec = m["apartado"]
        m["bloque"] = BLOQUES.get(sec.split(".")[0]) if sec else None
        m["apartado_titulo"] = APARTADOS.get(sec)
        if not m["titulo"] and not m["texto"]:
            m["pendiente"] = True
            m["texto"] = PENDIENTE
        final.append(m)

    nums = [m["n"] for m in final]
    faltan = sorted(set(range(1, max(nums) + 1)) - set(nums))
    dup = sorted({n for n in nums if nums.count(n) > 1})
    pend = [m["n"] for m in final if m.get("pendiente")]
    vacias = [m["n"] for m in final if not m.get("pendiente") and (not m["titulo"] or not m["texto"])]
    print(f"medidas: {len(final)}  max: {max(nums)}", file=sys.stderr)
    print(f"faltan: {faltan}", file=sys.stderr)
    print(f"duplicadas: {dup}", file=sys.stderr)
    print(f"pendientes de campaña: {pend}", file=sys.stderr)
    print(f"sin título o sin texto: {vacias}", file=sys.stderr)

    data = {
        "partido": "pp",
        "nombre": "Partido Popular",
        "documento": "La Reconstrucción Nacional. El programa del cambio necesario para España",
        "fuente": URL,
        "paginas": doc.page_count,
        "unidad": "Medida",
        "medidas": final,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"-> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
