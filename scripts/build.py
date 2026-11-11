"""Genera dist/index.html (Artifact) y docs/index.html (GitHub Pages)
incrustando los programas extraídos en la plantilla.

Lee data/partidos.json y, para cada partido, data/<id>.json si existe.
Uso:  python3 scripts/build.py
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "app/index.template.html"
OUT = ROOT / "dist/index.html"
DOCS = ROOT / "docs"
# {"url": "https://<ref>.supabase.co", "key": "<clave publishable/anon>"} (públicas)
SUPABASE = Path(os.environ.get("PAPELETA_SUPABASE", ROOT / "data/supabase.json"))


def main():
    partidos = json.loads((ROOT / "data/partidos.json").read_text())
    bundle = []
    for p in partidos:
        f = ROOT / f"data/{p['id']}.json"
        entry = dict(p)
        if f.exists():
            d = json.loads(f.read_text())
            entry["documento"] = d["documento"]
            entry["fuente"] = d["fuente"]
            entry["unidad"] = d.get("unidad", "Medida")
            entry["medidas"] = [
                {
                    "n": m["n"],
                    "p": m["pagina"],
                    "pf": m["pagina_fin"],
                    "pdf": m.get("pagina_pdf", m["pagina"]),
                    "a": m.get("apartado"),
                    "at": m.get("apartado_titulo"),
                    "b": m.get("bloque"),
                    "ti": m["titulo"],
                    "tx": m["texto"],
                    **({"pend": True} if m.get("pendiente") else {}),
                }
                for m in d["medidas"]
            ]
            entry["estado"] = "publicado"
        else:
            entry["medidas"] = []
        bundle.append(entry)

    data = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")  # seguro dentro de <script>
    html = TEMPLATE.read_text().replace("/*__DATA__*/[]", data)
    OUT.parent.mkdir(exist_ok=True)
    # El Artifact no lleva cuentas (su CSP bloquea otros servidores; usa su propia db)
    OUT.write_text(html.replace("<!--__CUENTAS__-->", ""))

    # La web pública lleva el módulo de cuentas si hay configuración de Supabase
    cuentas = ""
    if SUPABASE.exists():
        cfg = json.dumps(json.loads(SUPABASE.read_text()), separators=(",", ":"))
        js = (ROOT / "app/cuentas.js").read_text().replace("/*__SUPABASE__*/null", cfg)
        cuentas = '<script type="module">\n' + js + "</script>"
    html = html.replace("<!--__CUENTAS__-->", cuentas)
    # Página completa para GitHub Pages y para abrir en local. El Artifact
    # añade este mismo esqueleto al publicar dist/index.html.
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<meta name="description" content="Lee los programas electorales del 29N propuesta a propuesta, '
        'sin saber de qué partido es cada una, y descubre tu afinidad.">'
        '<meta name="theme-color" content="#e9ecf1">'
        "<style>:root{color-scheme:light;box-sizing:border-box;"
        "padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}"
        "body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}"
        "</style></head><body>" + html + "</body></html>\n"
    )
    (DOCS / ".nojekyll").touch()
    n = sum(len(p["medidas"]) for p in bundle)
    print(f"{OUT}  ({n} medidas, {OUT.stat().st_size // 1024} KB)")
    print(f"{DOCS / 'index.html'}  (GitHub Pages, cuentas: {'sí' if cuentas else 'no'})")


if __name__ == "__main__":
    main()
