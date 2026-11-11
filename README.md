# Papeleta 29N

App tipo Tinder para leerse los programas de las generales del 29 de noviembre
de 2026, propuesta a propuesta y sin saber de qué partido es cada una.

Web: https://julialopezgomez.github.io/papeleta-29n/

Cada tarjeta muestra una propuesta copiada tal cual del programa, con su número
de medida y su página. Al votar (Red flag, En contra, Neutral, A favor, Esencial)
se revela el partido y se actualiza tu afinidad con cada programa. En esta web
los votos se guardan en el navegador (`localStorage`): no se envían a ningún
servidor y no se sincronizan entre dispositivos.

## Estructura

- `fuentes/<partido>/` — PDFs oficiales descargados de la web de cada partido
  (no se suben al repositorio; la app enlaza siempre al PDF oficial).
- `scripts/extraer_<partido>.py` — extrae cada medida **literal** con su número y página.
  Cada PDF tiene una maquetación distinta, así que cada partido necesita su extractor.
- `scripts/verificar.py` — comprueba frase a frase que el texto extraído aparece tal cual en el PDF.
- `data/partidos.json` — lista de partidos, colores y estado (publicado / pendiente).
- `data/<partido>.json` — medidas extraídas.
- `app/index.template.html` — la app (HTML + JS sin dependencias).
- `scripts/build.py` — incrusta los datos en la plantilla y genera `docs/index.html`
  (la web de GitHub Pages, también sirve para abrir en local).

## Estado (11 nov 2026)

| Partido | Programa | Medidas |
|---|---|---|
| PP | «La Reconstrucción Nacional», [PDF](https://www.pp.es/wp-content/uploads/2026/11/LA-RECONSTRUCCION-NACIONAL.pdf), 82 págs. | 249 (241 con texto; 8 reservadas para la campaña) |
| PSOE | sin publicar | — |
| Vox | sin publicar | — |
| Frente Amplio | sin publicar | — |

## Añadir un programa nuevo

```bash
.venv/bin/python scripts/extraer_pp.py
.venv/bin/python scripts/verificar.py data/pp.json fuentes/pp/LA-RECONSTRUCCION-NACIONAL.pdf
python3 scripts/build.py
```

1. Descargar el PDF oficial a `fuentes/<id>/`.
2. Escribir `scripts/extraer_<id>.py` (mismo formato de salida que `extraer_pp.py`).
3. Verificar, reconstruir y subir `docs/index.html` (GitHub Pages se actualiza solo).

Los votos se guardan por medida (`partido:número`), así que añadir partidos o
volver a publicar no borra nada.
