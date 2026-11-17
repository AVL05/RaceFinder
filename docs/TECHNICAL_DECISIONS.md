# Decisiones técnicas

## Entorno real inspeccionado (2026-11-16)
Windows 11, Node 24, npm 11, Python **no instalado** (se instaló 3.12.10 con winget), CPU i7-12650H, 16 GB RAM, GPU **RTX 3050 Laptop 4 GB** (driver 621.24). Difiere del equipo descrito en el encargo (RTX 5060 Ti 8 GB, 32 GB); se diseñó para el hardware real, con CPU como camino base. Todo escala al equipo mayor.

## Decisiones
| Tema | Decisión | Justificación |
|---|---|---|
| OCR | **RapidOCR** (`rapidocr-onnxruntime` 1.4.4, Apache-2.0) | Mismos modelos PP-OCR de PaddleOCR vía ONNX Runtime: evita instalar `paddlepaddle` (grande, frágil en Windows) y comparte runtime con el futuro reconocimiento facial. Verificado funcionando en CPU. |
| Localización de dorsal | DBNet + filtros + mosaico | No hay un detector de dorsales libre verificado. OCR sobre la foto completa pierde dorsales pequeños; el mosaico lo mitiga. Mejora futura: detector de personas + clasificador de dorsal con datos propios. |
| Backend | FastAPI + SQLite (WAL) + hilo trabajador | Mínima complejidad para MVP; estado persistente sin broker. |
| Frontend | React 19, Vite 8, Tailwind 4, lucide-react, JavaScript | Según el encargo. Tests con Vitest + Testing Library. |
| Almacenamiento | Originales direccionados por SHA-256 | Dedupe gratis, rutas seguras, bytes idénticos. |
| Subida de carpetas | `webkitdirectory` y `DataTransfer` | El navegador no expone rutas locales; se sube a la copia local. Duplica el espacio en disco (ver ROADMAP: modo "indexar in situ"). |
| GPU | **No instalada** en el MVP | `onnxruntime-gpu` 1.32 existe, pero conflicta con `onnxruntime` CPU y no se ha medido la necesidad; 3050 4 GB sirve para OCR, pero no se ha verificado. Pendiente de medir en Fase 3. |
| Exportación | ZIP_STORED | No recomprime los originales. |

## Licencias (verificar de nuevo antes de distribuir)
- RapidOCR y PP-OCR: Apache-2.0. FastAPI, React, Vite, Tailwind, lucide: MIT/ISC. Pillow: HPND. OpenCV: Apache-2.0. onnxruntime: MIT.
- **Reconocimiento facial (Fase 2):** el *código* de InsightFace es MIT, pero según su documentación los **modelos preentrenados (p. ej. buffalo_l) son solo para investigación no comercial**. Es válido para uso personal local; **no** para distribuir públicamente o comercializar. Alternativas a evaluar en Fase 2 con licencia permisiva comprobada (p. ej. modelos con licencia explícita Apache/MIT) o entrenar/obtener licencia. Esta nota procede de mi conocimiento previo; no se ha consultado en línea en esta sesión y debe confirmarse en la fuente oficial.
- Datos biométricos (RGPD): consentimiento explícito, finalidad limitada, borrado bajo demanda, sin base de identidades.

## Riesgos técnicos
1. Precisión OCR en fotos reales (movimiento, dorsal doblado, ángulo): **sin medir**.
2. Falsos positivos de números ajenos al dorsal.
3. Rendimiento en 10 000 fotos: OCR en CPU ≈ varios segundos/foto (no medido en fotos reales); la cola es reanudable.
4. Duplicación de disco al importar.
5. Compatibilidad de Blackwell (5060 Ti) con ONNX Runtime CUDA: por comprobar en ese equipo.
6. Dependencia `opencv-python` y `-headless` pueden solaparse: se fijó solo `headless`.

## Reconocimiento facial (v0.3)
| Tema | Decisión | Justificación |
|---|---|---|
| Modelos | **YuNet** (detección, MIT) + **SFace** (vector de 128 dimensiones, Apache-2.0), de OpenCV Zoo | Ya incluidos en `opencv-python-headless` (`cv2.FaceDetectorYN` / `cv2.FaceRecognizerSF`): sin dependencias nuevas, CPU rápida (~20 ms detección, ~35 ms por cara). A diferencia de los modelos preentrenados de InsightFace (solo uso no comercial), estas licencias permiten distribuir la app. |
| Descarga | Bajo demanda, la primera vez que se activa, verificando SHA-256; se guardan en `backend/models/` (ignorado por git) | La función es opcional; quien no la usa no descarga 38 MB. |
| Semilla de la búsqueda | Las caras **encima del dorsal** buscado (alineadas con el torso, a distancia y escala plausibles); si hay ≥3, se marca la que no se parece al resto | No se asume que una cara y un dorsal de la misma foto son la misma persona: se proponen y el usuario confirma o desmarca. |
| Coincidencia | Coseno máximo contra las caras elegidas; umbral 0,363 (recomendado por OpenCV para SFace), "alta" ≥ 0,5 | Se muestra como "parecido alto/medio" y el valor bruto en un tooltip; no es una probabilidad. |
| Privacidad | Desactivado por defecto; consentimiento explícito; vectores anónimos sin nombres; botón para borrar todos los datos faciales (vectores y recortes) | Datos biométricos: minimización y borrado bajo demanda. |

Sin validar: la precisión con fotos reales de carreras (gorras, gafas, caras de perfil o pequeñas). La prueba de extremo a extremo se hizo con caras reales de las imágenes de ejemplo de OpenCV pegadas sobre corredores sintéticos, lo que solo demuestra que el flujo funciona.
