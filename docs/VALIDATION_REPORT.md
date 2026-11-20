# Estado de la validación

## Versión publicada

La comprobación de GitHub Actions para el commit `c19ce1612b88db358398e32677e6b3a198d2cee6` terminó correctamente en Windows con Node 24, Python 3.12 y CPU. Pasaron la compilación, 111 pruebas de backend y 8 pruebas de navegador en Chromium. [Ejecución de GitHub Actions](https://github.com/AVL05/RaceFinder/actions/runs/44718180004)

El autor confirmó que la búsqueda por dorsal y por cara funcionó en su prueba con fotos propias. La comprobación fue manual y cualitativa. Para obtener cifras reproducibles se necesitan fotos etiquetadas de distintos eventos. [Guía de evaluación](EVALUATION.md)

## Validación técnica del 16 de noviembre de 2026

Este registro corresponde a una revisión anterior. Se conserva como evidencia de los defectos corregidos y de cómo se comprobaron. Las cifras de pruebas y rendimiento de esta sección corresponden a esa revisión.

Equipo de la revisión: Windows 11, i7-12650H, 16 GB, RTX 3050 Laptop (sin uso de GPU) · OpenCV 5.0.0 · Playwright 1.65.1 (Chromium)

### 1. Resumen

- **Métricas con fotos reales: pendientes.** El proyecto no tiene fotos reales de carreras y no se han buscado fuera de él, por privacidad. **No se informa de ninguna cifra de precision, recall o F1.** Queda listo el mecanismo para medirlas: [EVALUATION.md](EVALUATION.md).
- Se han encontrado y corregido **8 defectos**. Los más importantes:
  - Un vector facial borrado seguía en disco, en el diario WAL de SQLite.
  - La API permitía activar el reconocimiento facial sin consentimiento.
  - Las lecturas de dorsal dudosas elegían caras de referencia.
- Pruebas: **55 tests de backend** y **6 pruebas E2E con Playwright** en un navegador real, todas pasando. Dos correcciones se verificaron además con pruebas de mutación: se reintroduce el defecto y se comprueba que el test falla.

### 2. Defectos encontrados y corregidos

| # | Defecto | Cómo se encontró | Corrección | Verificación |
|---|---|---|---|---|
| 1 | **Datos biométricos recuperables tras "Borrar todos los datos faciales"**: `DELETE` + `VACUUM` dejaban copias de los vectores en `racefinder.sqlite3-wal`. | Test que busca los bytes del vector en los archivos de la base de datos. | `PRAGMA wal_checkpoint(TRUNCATE)` tras `VACUUM`. | `test_delete_all_biometric_data`: antes del borrado el vector **sí** está en disco (control) y después no. Mutación: sin el checkpoint el test falla. |
| 2 | **Consentimiento solo en la interfaz**: `PUT /api/settings {"faces_enabled": true}` activaba el análisis facial sin más. | Auditoría de la API. | Activar exige `face_consent: true` (si no, 422). Se guarda la fecha del consentimiento y se elimina al borrar los datos. | `test_consent_required_at_api_level` y E2E "consentimiento". |
| 3 | **Recortes de caras en la caché del navegador** (`no-cache` permite guardarlos) y accesibles con la función desactivada. | Auditoría. | `Cache-Control: no-store`. El endpoint devuelve 409 si la función está desactivada o tras el borrado. | Tests de borrado (API y E2E). |
| 4 | **La comprobación "¿otra persona?" estaba sesgada**: comparaba cada cara con una media que la incluía. Con 3 caras asociadas (el mínimo) no detectaba a un intruso (similitud 0,48 > 0,363). | Revisión del cálculo y verificación numérica. | Media "dejando una fuera" (similitud del intruso 0,04). | `test_consistency_is_leave_one_out`. Mutación: con la media antigua el test falla. |
| 5 | **Las lecturas de dorsal dudosas preseleccionaban caras de referencia**: un 184 mal leído sobre otra persona sembraba la búsqueda con una cara ajena. | Auditoría. | Solo preseleccionan las lecturas fiables o confirmadas. Las dudosas se muestran con la marca "dorsal dudoso" y el usuario puede elegirlas. | `test_doubtful_bib_does_not_preselect_face`. |
| 6 | **La interfaz y el backend usaban reglas de preselección distintas**, así que la evaluación no medía lo que ve el usuario. | Auditoría. | La lógica vive en `faces.candidates_for_bib` / `faces.search` y la usan la API, la evaluación y la interfaz (campo `preselect`). | Test de métricas de búsqueda y E2E. |
| 7 | **El visor se cerraba de golpe** al descartar un dorsal en una búsqueda (la foto salía de los resultados). | E2E con Playwright. | El visor conserva su lista mientras está abierto. | E2E "revisión manual". |
| 8 | **Modelo YuNet no recomendado para OpenCV 5**: `2023mar` tiene entrada fija; OpenCV Zoo recomienda `2026may` (dinámica) para 5.x. | Lectura del README oficial. | Se pasa a `2026may`. Antes se comprobó que en OpenCV 5.0.0 da **las mismas detecciones** (mismo número de caras, IoU 1,0, 2 imágenes × 3 escalas). | Hash verificado al descargar; tests y E2E con el modelo nuevo. |

Ningún umbral se ha cambiado: el de cara sigue en 0,363 (el publicado por OpenCV para SFace) y el de lectura dudosa en 0,85.

### 3. Comprobaciones realizadas

#### Catálogo y revisión
- Las fotos sin coincidencias no desaparecen. Tras buscar por dorsal y por cara, `/api/photos` devuelve todas; la foto sin corredores aparece en "Sin dorsal leído" (test de API y E2E).
- Las lecturas dudosas siguen en la búsqueda, en "Por revisar" (`match: doubtful`).
- Desde el visor se puede añadir un dorsal a mano, confirmar o descartar. Descartar un dorsal no borra la foto (E2E).

#### Asociación cara–dorsal en fotos con varios corredores
Son tests de geometría, no de precisión:
- Dos corredores lado a lado: cada dorsal se queda con su cara.
- Corredor en primer plano con una cara pequeña alineada detrás: gana la del primer plano.
- Se rechazan caras de escala o distancia imposibles, y no se asocia nada si no hay cara.

#### Consentimiento y datos biométricos
- **Desactivado por defecto.** Sin consentimiento la API rechaza activarlo y no se procesa ninguna cara (`faces.count = 0`).
- **Qué se borra con "Borrar todos los datos faciales":**
  - La tabla `faces`.
  - Los recortes de caras en `data/crops`.
  - La fecha del consentimiento.
  - Las páginas libres de la base de datos (`VACUUM`) y el diario WAL.
- **Qué no se borra, y por qué:**
  - Las fotos, miniaturas y vistas previas son copias de las fotos, no datos biométricos derivados.
  - Los modelos ONNX no contienen datos personales.
- **Al quitar una foto** se borran en cascada sus caras y todos sus recortes.
- **Herramienta de evaluación:** procesar caras exige `--consiento`.

#### Modelos (detalle en [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md))

| Modelo | SHA-256 | Licencia (verificada en el `LICENSE` oficial) |
|---|---|---|
| `face_detection_yunet_2026may.onnx` | `ebafce4e…22f0f0` | MIT (Shiqi Yu) |
| `face_recognition_sface_2021dec.onnx` | `0ba9fbfa…4e79` | Apache-2.0 |

La descarga se verifica por SHA-256 antes de usarse. Se documentan las atribuciones y el texto MIT exigido para redistribuir.

#### Pruebas de navegador con servidor real y biblioteca aislada
1. Importar 7 fotos → todas en el catálogo, incluida la que no tiene nada.
2. Buscar el dorsal 184 → 2 fotos; añadir un 184 a mano y descartarlo; la foto sigue existiendo.
3. Consentimiento: sin la casilla, *Activar* está deshabilitado y la API devuelve 422.
4. Búsqueda por cara: preselecciona las 2 caras situadas sobre el 184 y encuentra las 2 fotos sin dorsal de esa persona. Ninguna de la otra persona. Desmarcar todas vacía los resultados por cara sin tocar los del dorsal. Sin scroll horizontal a 390 px.
5. Borrado de datos faciales desde Ajustes: 0 vectores, recortes con 409, las fotos intactas.
6. Etiquetado con "corredores sin dorsal legible" y etiquetas de cara.

**Los fixtures del E2E** pegan dos caras reales de las imágenes de ejemplo de OpenCV sobre corredores sintéticos. Solo sirven para comprobar que la interfaz funciona; **no** se usan como evaluación, porque al ser la misma cara pegada las similitudes son artificialmente altas.

### 4. Rendimiento medido (no son métricas de precisión)
- **SFace:** ~36 ms por cara (alineado + vector), con una cara de `messi5.jpg`, en CPU.
- **YuNet:** ~20 ms por detección en `messi5.jpg` (548×342). Con fotos de carrera, a 2560 px de lado largo, el tiempo será mayor: se mide con `eval_folder.py`, que informa del tiempo medio por foto de OCR y de caras.

### 5. Observación sin métrica, a revisar con datos reales
En la imagen oficial `largest_selfie.jpg` de OpenCV Zoo, YuNet detecta **58 caras a 2048 px y 122 a 3482 px**. RaceFinder detecta a un máximo de 2560 px de lado largo y descarta caras de menos de 22 px. En fotos de 24 MP con corredores lejanos se perderán caras pequeñas. **No se ha cambiado** porque no hay datos reales que justifiquen el coste extra. Es lo primero que conviene medir en la partición `tune`, con la etiqueta `cara_pequena`.

### 6. Limitaciones pendientes
1. **Sin métricas reales** de OCR, de búsqueda por cara ni de asociación. Ver [EVALUATION.md](EVALUATION.md).
2. **Asociación cara–dorsal**: no se mide directamente (no hay etiquetas por cara). Se mide de forma indirecta con los falsos positivos de la búsqueda por cara.
3. **Perfiles, gafas de sol, gorras y caras pequeñas**: preparados como etiquetas de evaluación y sin medir. Es esperable que SFace (MobileFaceNet) pierda precisión con perfiles marcados.
4. **Umbrales sin calibrar** con datos propios: 0,363 para cara y 0,85 para lectura dudosa.
5. **Búsqueda por cara a partir de una sola foto con dorsal**: la comprobación de coherencia necesita al menos 3 caras asociadas. Con 1 o 2 depende solo de la revisión del usuario.
6. **Caché del navegador**: las vistas previas de las fotos (no biométricas) siguen en caché tras borrar los datos faciales. Los recortes de caras ya no se guardan (`no-store`). Las respuestas que se cachearon antes de esta versión pueden seguir en la caché del navegador hasta que se vacíe.
7. **GPU**. Esta revisión se ejecutó en CPU. La configuración actual se detalla en la [guía de operación](OPERATIONS.md#aceleración-por-gpu).

### Aportar evidencia

Si puedes evaluar una carrera, sigue el [procedimiento de etiquetado y evaluación](EVALUATION.md) y comparte resultados agregados con el tamaño de la muestra y el equipo usado.
