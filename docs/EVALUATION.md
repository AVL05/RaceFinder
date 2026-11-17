# Evaluación con fotos reales

**Estado: pendiente.** No hay fotos reales de carreras accesibles en el proyecto, así que **no se publica ninguna métrica de precisión**. Todo lo que hay abajo es el procedimiento para obtenerlas.

## Opción A: herramienta de línea de órdenes (recomendada)

Trabaja sobre una biblioteca aislada en `data_eval/` (ignorada por git). No toca tu biblioteca `data/` ni modifica los originales.

```powershell
cd backend
.venv\Scripts\python.exe tools\eval_folder.py plantilla "D:\fotos\maraton"
```

Rellena `D:\fotos\maraton\racefinder-etiquetas.json` (borra las entradas de las fotos que no quieras evaluar):

```json
"IMG_0012.jpg": {"bibs": ["184"], "present": ["77"], "tags": ["gorra"]}
```

| Campo | Qué poner |
|---|---|
| `bibs` | Dorsales que una persona puede **leer** en esa foto. |
| `present` | Corredores que **salen** en la foto aunque su dorsal no se lea. Sirve para medir la búsqueda por cara. |
| `tags` | Opcional: `inclinado`, `ocluido`, `pequeno`, `varios_corredores`, `fondo_complejo`, `cartel_reloj`, `poca_luz`, `desenfocado`, `cara_pequena`, `perfil`, `gafas`, `gorra`. |

```powershell
.venv\Scripts\python.exe tools\eval_folder.py evaluar "D:\fotos\maraton" --caras --consiento
```

Genera `informe-evaluacion.md` y `informe-evaluacion.json`, e indica cómo abrir esa biblioteca en la web para revisar los fallos. Sin `--caras` solo se mide el dorsal; `--consiento` es obligatorio para procesar caras.

## Opción B: desde la web
Arranca con otra carpeta de datos (`$env:RACEFINDER_DATA="D:\eval-racefinder"; pnpm run dev`), importa las fotos y entra en *Ajustes → Medir la precisión*. Se etiqueta foto a foto con los mismos campos. Después:
- *Evaluar OCR*: vuelve a ejecutar el lector y mide también los tiempos (y los de las caras, si están activadas).
- *Evaluar búsqueda (dorsal + cara)*: mide lo que ve el usuario, con las lecturas y caras ya guardadas.

## Qué se mide

**OCR** (pares foto–número):
- Precision, recall, F1, falsos positivos y falsos negativos.
- Por foto: todos los dorsales encontrados, al menos uno, conjunto exacto y falsas alarmas en fotos sin dorsal legible.
- Desglose por condición.
- Tiempo medio, mediana, p95 y total.

**Búsqueda**: para cada dorsal etiquetado como legible en al menos una foto, la verdad son las fotos en las que ese corredor aparece (`bibs` ∪ `present`). Se compara con tres modos:
- *Solo dorsal*: incluye las lecturas dudosas, que la web muestra en "Por revisar".
- *Solo cara*: semilla con las caras preseleccionadas, igual que la web.
- *Dorsal o cara*.

Se informa de precision, recall y F1 de cada modo, de la **recuperación de fotos sin dorsal legible por la cara** y del desglose por condición (`perfil`, `gafas`, `gorra`, `cara_pequena`…).

## Metodología
- **Particiones:** cada foto va de forma determinista (por su SHA-256) a `tune` (≈30 %) o `test` (≈70 %). Los umbrales (`MATCH_THRESHOLD`, `doubtful_below`, parámetros del OCR) **solo** se ajustan mirando `tune`. `test` es la validación final: la web exige confirmarlo y registra cuántas veces se ha ejecutado.
- **Tamaño de la muestra:** con menos de 30 fotos por partición las cifras se marcan como orientativas. Para la búsqueda por cara conviene que haya varios corredores que salgan en ≥3 fotos, con y sin dorsal legible.
- **Etiquetado:** una foto con un dorsal ilegible no cuenta como fallo del OCR (no va en `bibs`), pero sí como fallo de la búsqueda si ese corredor sale y no se encuentra (va en `present`).
- **Asociación cara–dorsal:** no hay etiquetas por cara, así que no se mide su exactitud de forma directa. Se mide indirectamente con la búsqueda por cara: una asociación equivocada produce falsos positivos.
