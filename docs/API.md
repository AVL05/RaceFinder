# API local

La interfaz y las herramientas locales hablan con FastAPI por HTTP. Usa el puerto de API impreso en la terminal. Con el puerto habitual, FastAPI publica Swagger en [localhost:8000/docs](http://127.0.0.1:8000/docs), ReDoc en [localhost:8000/redoc](http://127.0.0.1:8000/redoc) y el esquema en [localhost:8000/openapi.json](http://127.0.0.1:8000/openapi.json). Estos enlaces requieren que RaceFinder esté abierto en ese puerto.

La API actual está pensada para la aplicación y para scripts en el mismo equipo. No requiere inicio de sesión. Un álbum delimita consultas, pero cualquier cliente con acceso a la API puede consultar la biblioteca. Para las condiciones de acceso y los puertos, consulta la [guía de operación](OPERATIONS.md).

## Consultas de ejemplo

Ejecuta estas órdenes en PowerShell. Sustituye `8000` por el puerto anunciado.

```powershell
$base = 'http://127.0.0.1:8000'
Invoke-RestMethod "$base/api/health"
Invoke-RestMethod "$base/api/albums"
Invoke-RestMethod "$base/api/search?bib=184&mode=exact"
Invoke-WebRequest "$base/api/export/catalog.csv?filter=favorites" -OutFile .\favoritas.csv
```

La búsqueda devuelve una lista dentro de `results`. Cada elemento incluye la foto y su tipo de coincidencia (`exact`, `doubtful` o `similar`). Trata los dorsales como cadenas de entre uno y cinco dígitos para preservar ceros iniciales. Usa el `id` de la foto para los recursos del visor y de exportación.

## Estado y catálogo

| Operación | Uso |
| --- | --- |
| `GET /api/health` | Diagnóstico de la API, dispositivos efectivos y número de trabajadores. |
| `GET /api/stats` | Totales, estado del OCR y del índice facial. Acepta `album`. |
| `GET /api/albums` | Listar álbumes con sus recuentos y rangos. |
| `POST /api/albums` | Crear con `name`, `min_number` y `max_number` opcionales y una lista inicial opcional `ids`. |
| `PATCH /api/albums/{album}` | Guardar nombre y rango. Para heredar el rango general, envía ambos límites como `null`. |
| `DELETE /api/albums/{album}` | Quitar el álbum y sus asociaciones. |
| `POST /api/albums/{album}/photos` | Cambiar la pertenencia mediante `{"action":"add","ids":[1]}` o `remove`. |
| `GET /api/photos` | Listar fotos. Acepta `offset` y `limit`, entre 1 y 1.000 por página, además de los filtros del catálogo. |
| `GET /api/photos/selection` | Obtener IDs de la vista filtrada, hasta 20.000. |
| `GET /api/photos/{pid}` | Consultar detalle y dorsales. Acepta `album`. |
| `PUT /api/photos/favorites` | Aplicar `{"ids":[1],"favorite":true}` o quitar el favorito con `false`. |
| `GET /api/photos/{pid}/thumb` | Obtener miniatura. |
| `GET /api/photos/{pid}/preview` | Obtener vista previa para el visor. |
| `GET /api/photos/{pid}/original` | Obtener el original. `download=true` lo entrega como adjunto. |
| `DELETE /api/photos/{pid}` | Quitar una foto de toda la biblioteca de RaceFinder. |
| `POST /api/photos/delete` | Quitar un lote, con `{"ids":[1,2]}`. |
| `POST /api/photos/delete-all` | Vaciar las fotos de toda la biblioteca. Requiere `{"confirm":"ELIMINAR"}`. |

Listado, selección y CSV usan `album`, `filename`, `filter` y `sort`. Los valores de `filter` son `all`, `with_bib`, `no_bib`, `pending`, `error`, `favorites` y `review`. Los de `sort` son `recent`, `oldest`, `name` y `name_desc`. El listado admite además `status` con estados separados por comas.

## Importación y análisis

| Operación | Uso |
| --- | --- |
| `POST /api/photos` | Importar con `multipart/form-data`. Repite el campo `files` por cada archivo y añade `album` a la URL si procede. La respuesta da el resultado de cada archivo, incluidos duplicados y rechazos. |
| `POST /api/photos/known` | Comprobar huellas rápidas para reanudar. El cuerpo `items` contiene pares `size` y `head`, el SHA-256 de los primeros 64 KiB en hexadecimal. Acepta `album`. |
| `POST /api/system/pick-folder` | Abrir un selector en el equipo anfitrión, con `title` opcional. |
| `POST /api/import/folder` | Iniciar la importación desde una ruta del anfitrión con `path` y `album` opcional. |
| `GET /api/import/status` | Consultar el progreso de la importación por carpeta. |
| `POST /api/import/cancel` | Solicitar que se detenga la importación por carpeta. Los archivos ya importados quedan en la biblioteca. |
| `GET /api/settings` | Leer modo, rango general, estado facial y fecha del consentimiento. |
| `PUT /api/settings` | Enviar la configuración deseada. Los campos omitidos toman valores predeterminados. `mode` admite `fast`, `balanced` y `thorough`. Para habilitar caras, envía conjuntamente `faces_enabled: true` y `face_consent: true`. |
| `POST /api/process` | Reanudar el análisis. `reprocess_errors` vale `true` por defecto. `reanalyze=true` vuelve a poner en cola las fotos analizadas. |
| `POST /api/process/cancel` | Pausar la toma de nuevos trabajos de análisis. |
| `POST /api/photos/{pid}/reprocess` | Poner una foto en cola para reprocesar. |

## Búsqueda, revisión y exportación

| Operación | Uso |
| --- | --- |
| `GET /api/bibs/index` | Dorsales con recuento de fotos. Acepta `album` y `limit` (300 por defecto, máximo 2.000). |
| `GET /api/bibs/{bid}/crop` | Recorte de una lectura con caja de detección. |
| `GET /api/search` | Buscar `bib`, con `mode=exact` o `mode=similar`, `album` opcional, `min_conf` y `limit` (1.000 por defecto, máximo 5.000). |
| `POST /api/photos/{pid}/bibs` | Añadir un dorsal con `{"number":"184"}`. |
| `PATCH /api/bibs/{bid}` | Revisar una lectura con `{"review":"confirmed"}`, `rejected` o `auto`. |
| `GET /api/export/catalog.csv` | Exportar la vista según sus filtros. CSV UTF-8 con BOM y delimitador de punto y coma. |
| `POST /api/export/save` | Copiar originales al disco anfitrión. Cuerpo con `ids`, `dest` absoluto, `subfolder` opcional y `open_after` (por defecto `true`). Devuelve copias, omisiones, fallos y destino. |
| `POST /api/export` | Obtener un ZIP por streaming. Cuerpo JSON con `ids`. |
| `POST /api/export/download` | Obtener el mismo ZIP desde un formulario con `ids=1,2`. |

## Búsqueda por cara y evaluación

| Operación | Uso |
| --- | --- |
| `GET /api/faces/for-bib` | Obtener candidatos para el `bib` y el `album` opcional. `preselect` indica las referencias sugeridas. Devuelve hasta 60 candidatos. |
| `POST /api/faces/search` | Buscar por referencias elegidas con `{"face_ids":[1,2]}`. Acepta entre 1 y 200 referencias, `album` opcional y `limit` (500 por defecto, máximo 5.000). Devuelve similitud coseno. |
| `GET /api/faces/{fid}/crop` | Obtener un recorte facial con `Cache-Control: no-store`. |
| `DELETE /api/faces` | Borrar el índice y los recortes faciales, retirar el consentimiento y desactivar la función. |
| `GET /api/eval/summary` | Resumen de etiquetas, particiones y estado. |
| `GET /api/eval/photos` | Listar fotos para etiquetar por `state`, `limit` y `offset`. |
| `PUT /api/eval/labels/{pid}` | Guardar `state` (`labeled` o `no_bib`), `bibs`, `present` y `tags`. |
| `DELETE /api/eval/labels/{pid}` | Quitar la etiqueta de una foto. |
| `POST /api/eval/run` | Iniciar evaluación de OCR. Envía `split` y, si quieres ajustar parámetros para esa ejecución, `params`. |
| `POST /api/eval/search-run` | Medir la búsqueda contra etiquetas usando el índice existente. |
| `GET /api/eval/status` | Consultar el estado de la ejecución de OCR. |
| `GET /api/eval/runs` | Consultar el historial guardado. |

Las evaluaciones aceptan `split: "tune"` o `"test"`. Para `test` envía también `confirm_test: true`. [Guía de evaluación](EVALUATION.md)

## Errores

- `404` indica que el recurso solicitado no existe. Una búsqueda válida sin coincidencias devuelve una lista vacía.
- `409` indica un conflicto de estado, por ejemplo una consulta facial con la función desactivada o un proceso incompatible en curso.
- `422` indica parámetros o campos inválidos o una confirmación de borrado requerida. FastAPI devuelve el detalle en `detail`.
- `507` indica falta de espacio cuando la operación puede detectarla antes de escribir. En importaciones por lote, revisa también los errores por archivo en el cuerpo de la respuesta.
