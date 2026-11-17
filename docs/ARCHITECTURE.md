# Arquitectura

```
Navegador (React + Vite + Tailwind)
   │  fetch /api/*   (en desarrollo Vite proxifica; en producción FastAPI sirve frontend/dist)
   ▼
FastAPI (127.0.0.1:8000) ── SQLite (WAL) ── data/{originals,thumbs,tmp}
   │
   └─ Worker (hilo único) ── BibReader ── RapidOCR (ONNX Runtime)
```

## Estructura
```
backend/app/  config.py  db.py  imaging.py  bibs.py  worker.py  main.py
backend/tests/  unit, API y OCR real sobre imágenes sintéticas
frontend/src/  App.jsx  Lightbox.jsx  api.js  tests
data/  (ignorado por git) originals/ab/<sha256>.jpg · thumbs/ · tmp/ · racefinder.sqlite3
```

## Flujo de importación
1. El navegador envía lotes (≤25 ficheros / 40 MB) a `POST /api/photos`.
2. Cada fichero se escribe en `tmp/` con límite de tamaño, se hashea y se valida con Pillow (formato real, píxeles máximos).
3. Se mueve a `originals/<sha[:2]>/<sha>.<ext>` sin recodificar. Si el hash existe, se marca duplicado. El nombre del cliente solo se guarda para mostrarlo: **nunca construye rutas**.
4. Se genera la miniatura y se inserta la fila con `ocr_status='pending'`; se despierta al worker.

## Pipeline de dorsales (`bibs.py`)
Sin modelo de dorsales dedicado (no hay uno libre y fiable verificado). Estrategia: DBNet detecta regiones de texto en la imagen reducida a 1920 px y, si la foto es grande, en un mosaico 2×2 solapado sobre una versión de ~3200 px; el reconocedor lee cada región; se filtran tokens de 1–5 dígitos con caja de tamaño/proporción plausibles; se fusionan duplicados por IoU. Letras confundibles (O, I, S, B…) solo se convierten si el token ya es mayoritariamente numérico. Se guarda la caja en coordenadas de la imagen original como evidencia.

Limitación conocida: sin segmentar corredores, un número de otro texto (cartel, reloj) puede aparecer como dorsal; se mitiga con revisión manual. Mejora prevista: detector de personas/torso para acotar la búsqueda y un clasificador de "es dorsal".

## Esquema SQLite
- `photos(id, sha256 UNIQUE, original_name, ext, size, width, height, added_at, ocr_status, ocr_error, ocr_engine)`
- `bib_detections(id, photo_id→photos ON DELETE CASCADE, number, raw_text, confidence, bbox JSON, review auto|confirmed|rejected|manual)`
- `jobs(...)` reservada para cola multi-tipo (Fase 2); hoy el estado de la cola se deriva de `photos.ocr_status`.

## Cola, cancelación y reanudación
El estado vive en SQLite. Un hilo toma la foto `pending` más antigua. Cancelar termina la foto en curso y pausa. Al arrancar, `processing` vuelve a `pending`. Reprocesar reemplaza solo detecciones `auto`, conservando revisiones manuales.

## API
`GET /api/health|stats|photos|photos/{id}/thumb|photos/{id}/original|search?bib=&mode=exact|similar&min_conf=` · `POST /api/photos|process|process/cancel|photos/{id}/reprocess|photos/{id}/bibs|export` · `PATCH /api/bibs/{id}` · `DELETE /api/photos/{id}`.

## Seguridad
Escucha solo en 127.0.0.1; `TrustedHostMiddleware` (anti DNS-rebinding); CORS limitado a localhost; validación por contenido; rutas derivadas solo de SHA-256 validado; temporales `.part` eliminados en error y al apagar; sin telemetría ni peticiones salientes en tiempo de ejecución (RapidOCR incluye sus modelos en el paquete). No hay autenticación: es una app de un solo usuario local.

## Arranque (`scripts/dev.mjs`)
`pnpm run dev` crea `backend/.venv` si falta, reinstala dependencias de Python solo cuando cambia `requirements.txt`, instala las del frontend si faltan, busca puertos libres (API desde 8000, interfaz desde 5173), arranca uvicorn y Vite y abre el navegador. El backend se reinicia al guardar un `.py` mediante un vigilante propio (el `--reload` de uvicorn se queda colgado en Windows cuando el proceso no tiene consola). `RACEFINDER_DEV=1` hace que la API no sirva `frontend/dist`. `pnpm start` compila la interfaz y la sirve desde la API.

## Endpoints añadidos en la v0.2
`GET /api/photos?filter=with_bib|no_bib|pending|error`, `GET /api/photos/{id}`, `GET /api/bibs/index` (dorsales con nº de fotos), `GET /api/bibs/{id}/crop` (recorte del dorsal, cacheado en `data/crops`), `POST /api/photos/delete`, `POST /api/export/download` (ZIP en streaming desde formulario, sin pasar por disco ni memoria del navegador).
