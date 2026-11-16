# Papeleta 29N

App tipo Tinder para leerse los programas de las generales del 29 de noviembre
de 2026, propuesta a propuesta y sin saber de qué partido es cada una.

Web: https://julialopezgomez.github.io/papeleta-29n/

Cada tarjeta muestra una propuesta copiada tal cual del programa, con su número
de medida y su página. Al votar (Red flag, En contra, Neutral, A favor, Esencial)
se revela el partido y se actualiza tu afinidad con cada programa. Sin cuenta,
los votos se guardan solo en el navegador (`localStorage`); con cuenta (nombre y
contraseña), se guardan en Supabase y se ven desde cualquier dispositivo.

## Estructura

- `fuentes/<partido>/` — PDFs oficiales descargados de la web de cada partido
  (no se suben al repositorio; la app enlaza siempre al PDF oficial).
- `scripts/extraer_<partido>.py` — extrae cada medida **literal** con su número y página.
  Cada PDF tiene una maquetación distinta, así que cada partido necesita su extractor
  (`scripts/comun.py` tiene lo compartido: unir líneas, guiones, viñetas y negritas).
- `scripts/verificar.py` — comprueba frase a frase que el texto extraído aparece tal cual en el PDF.
- `data/partidos.json` — lista de partidos, colores y estado (publicado / pendiente).
- `data/<partido>.json` — medidas extraídas.
- `app/index.template.html` — la app (HTML + JS sin dependencias).
- `scripts/build.py` — incrusta los datos en la plantilla y genera `docs/index.html`
  (la web de GitHub Pages, también sirve para abrir en local).

## Estado (16 nov 2026)

Los cuatro programas están cargados. Cada frase de cada medida se comprueba
contra el PDF oficial con `scripts/verificar.py --todos`.

| Partido | Programa | Medidas | Referencia |
|---|---|---|---|
| PP | «La Reconstrucción Nacional», [PDF](https://www.pp.es/wp-content/uploads/2026/11/LA-RECONSTRUCCION-NACIONAL.pdf), 82 págs. | 249 (241 con texto; 8 reservadas para la campaña) | Medida N |
| PSOE | «La fuerza de seguir avanzando», [PDF](https://www.psoe.es/media-content/2026/11/PROGRAMAPSOE29N26.pdf), 114 págs. | 500 | Compromiso N |
| Vox | «Es sentido común», [PDF](https://www.voxespana.es/wp-content/uploads/2026/11/Programa-completo-A5-1.pdf), 66 págs. | 115 | Medida N |
| Frente Amplio | [PDF](https://frenteamplio.info/pdf/ProgramaFrenteAmplio.pdf), 151 págs. | 908 viñetas | Apartado X.Y · punto K (no numera sus medidas) |

Solo son tarjetas las medidas; las introducciones de cada capítulo o apartado
no. La página que se muestra es la impresa en el documento; el enlace abre el
PDF en la página correspondiente.

## Cuentas (Supabase)

Las cuentas son de nombre + contraseña, sin correo. No usan Supabase Auth: todo
está en `supabase/migrations/` y se despliega con la integración de GitHub de
Supabase al hacer push a `main` (igual que en sort-it-out-game).

- Las tablas viven en el esquema `privado`, que la API no expone.
- El navegador solo puede llamar a `papeleta_registrar`, `papeleta_entrar`,
  `papeleta_votos`, `papeleta_guardar`, `papeleta_salir` y `papeleta_borrar_cuenta`.
- Contraseñas con bcrypt; 10 intentos fallidos bloquean la cuenta 15 minutos.
- `data/supabase.json` (`{"url": …, "key": …}`) lleva la URL y la clave
  *publishable*, que son públicas. Nunca la clave secreta.

```bash
scripts/test-db.sh          # pruebas de las funciones en un Postgres temporal (Docker)
scripts/api-local.sh start  # API local en http://localhost:3000 para probar la web
```

## Añadir un programa nuevo

```bash
.venv/bin/python scripts/extraer_pp.py     # y extraer_psoe.py, extraer_vox.py, extraer_fa.py
.venv/bin/python scripts/verificar.py --todos
python3 scripts/build.py
```

1. Descargar el PDF oficial a `fuentes/<id>/`.
2. Escribir `scripts/extraer_<id>.py` (mismo formato de salida que `extraer_pp.py`).
3. Verificar, reconstruir y subir `docs/index.html` (GitHub Pages se actualiza solo).

Los votos se guardan por medida (`partido:número`), así que añadir partidos o
volver a publicar no borra nada.
