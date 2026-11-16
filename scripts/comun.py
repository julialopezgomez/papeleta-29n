"""Utilidades compartidas por los extractores de programas.

Cada extractor recorre el PDF con PyMuPDF, reconoce los elementos por su
tipografía y va añadiendo «trozos» de texto a la medida en curso. Aquí se
unen esos trozos en un texto literal:

- Se respeta el texto tal cual; solo se reconstruyen los cortes de línea.
- La negrita del original se marca como **así** (la app la muestra en negrita).
- Las viñetas internas de una medida empiezan línea con «• ».
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHY = "­"  # guion blando (corte de palabra al final de línea)


def spans(page, y_min=0, y_max=None):
    """Spans con texto de la página: dicts con font, size, color, x, y, x1, y1, text."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                if not s["text"].strip():
                    continue
                x0, y0, x1, y1 = s["bbox"]
                if y0 < y_min or (y_max is not None and y0 > y_max):
                    continue
                out.append({
                    "font": s["font"], "size": round(s["size"], 1), "color": s["color"],
                    "x": x0, "y": y0, "x1": x1, "y1": y1, "text": s["text"],
                    "bold": "Bold" in s["font"] or "Black" in s["font"],
                })
    return out


def lineas(sp, tol=3.5):
    """Agrupa spans en líneas (misma altura ± tol) ordenadas en lectura."""
    sp = sorted(sp, key=lambda s: (round(s["y"]), s["x"]))
    out = []
    for s in sp:
        if out and abs(out[-1][0]["y"] - s["y"]) <= tol:
            out[-1].append(s)
        else:
            out.append([s])
    for ln in out:
        ln.sort(key=lambda s: s["x"])
    return out


class Texto:
    """Acumula el texto de una medida respetando cortes de línea y negritas."""

    def __init__(self, guion_real=True):
        # guion_real=True: un «-» al final de línea es un guion de verdad
        # (público-privada) y se conserva; los cortes de palabra los marca el
        # guion blando U+00AD, que se elimina.
        self.guion_real = guion_real
        self.trozos = []  # (texto, negrita) ; "\n" = salto de línea forzado
        self.fin_linea = False

    def nueva_linea(self):
        self.fin_linea = True

    def salto(self, vineta=False):
        self.trozos.append(("\n• " if vineta else "\n", False))
        self.fin_linea = False

    def add(self, t, negrita=False, espacio=False):
        """espacio=True: en el PDF hay un hueco antes de este trozo (el espacio
        no está en el texto, solo en la posición)."""
        t = t.replace("\t", " ")
        if not t:
            return
        if espacio and self.trozos and not self.fin_linea:
            prev = self.trozos[-1][0]
            if not prev.endswith((" ", "\n")) and not t.startswith(" "):
                t = " " + t
        if self.fin_linea and self.trozos:
            prev, pb = self.trozos[-1]
            p = prev.rstrip(" ")
            if p.endswith(SHY):
                self.trozos[-1] = (p[:-1], pb)
                t = t.lstrip()
            elif p.endswith("-") and len(p) > 1 and p[-2].isalnum():
                self.trozos[-1] = (p, pb)
                if not self.guion_real and t[:1].islower():
                    self.trozos[-1] = (p[:-1], pb)
                t = t.lstrip()
            elif not prev.endswith((" ", "\n")) and not t.startswith(" "):
                t = " " + t
        self.fin_linea = False
        self.trozos.append((t, negrita))

    def vacio(self):
        return not "".join(t for t, _ in self.trozos).strip()

    def plano(self):
        return limpiar("".join(t for t, _ in self.trozos))

    def marcado(self):
        """Texto con la negrita como **…** (por tramos, sin partir palabras)."""
        segs = []
        for t, b in self.trozos:
            if t.startswith("\n"):
                b = False
            elif not t.strip():
                b = segs[-1][1] if segs else False
            if segs and segs[-1][1] == b and not t.startswith("\n"):
                segs[-1][0] += t
            else:
                segs.append([t, b])
        out = []
        for t, b in segs:
            core = t.strip()
            if b and core:
                lead = t[: len(t) - len(t.lstrip())]
                trail = t[len(t.rstrip()):]
                out.append(f"{lead}**{core}**{trail}")
            else:
                out.append(t)
        return limpiar("".join(out))


def con_huecos(ln, minimo=1.5):
    """(span, hay_hueco_antes) para cada span de una línea."""
    prev = None
    for sp in ln:
        yield sp, prev is not None and sp["x"] - prev["x1"] > minimo
        prev = sp


def limpiar(s):
    s = s.replace(SHY, "").replace(" ", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\*\* +", "** ", s)
    return s.strip()


def sin_marcas(s):
    return s.replace("**", "")


def guardar(partido, nombre, documento, fuente, medidas, unidad="Medida", numeradas=True):
    """Escribe data/<partido>.json e imprime un resumen de control."""
    nums = [m["n"] for m in medidas]
    print(f"{partido}: {len(medidas)} medidas", file=sys.stderr)
    if numeradas:
        faltan = sorted(set(range(1, max(nums) + 1)) - set(nums))
        dup = sorted({n for n in nums if nums.count(n) > 1})
        print(f"  máx {max(nums)} · faltan {faltan[:40]} · duplicadas {dup[:40]}", file=sys.stderr)
    vacias = [m["n"] for m in medidas if not m["texto"].strip()]
    if vacias:
        print(f"  sin texto: {vacias[:40]}", file=sys.stderr)
    largos = sorted(medidas, key=lambda m: -len(m["texto"]))[:3]
    print("  más largas: " + ", ".join(f"{m['n']}({len(m['texto'])})" for m in largos), file=sys.stderr)
    data = {
        "partido": partido, "nombre": nombre, "documento": documento,
        "fuente": fuente, "unidad": unidad, "medidas": medidas,
    }
    out = ROOT / f"data/{partido}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"  -> {out}", file=sys.stderr)
