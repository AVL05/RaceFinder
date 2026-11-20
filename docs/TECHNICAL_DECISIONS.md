# Decisiones técnicas

Este registro recoge decisiones vigentes y las condiciones que conviene preservar al modificarlas. [Arquitectura](ARCHITECTURE.md)

| Área | Decisión | Motivo |
| --- | --- | --- |
| Ejecución | React y FastAPI en el equipo que guarda la biblioteca. | Permite usar el procesador y el disco locales, mantener el uso independiente de un servicio remoto y conservar un arranque común. |
| Persistencia | SQLite en modo WAL y estados por foto. | La biblioteca y la cola se recuperan juntas. Las reclamaciones atómicas coordinan los trabajadores y los estados permiten reintentar. |
| Importación | Originales por SHA-256 y pertenencia a álbumes por asociación. | Evita originales duplicados por contenido y permite que una foto esté en varias carreras o colecciones. Los enlaces duros pueden ahorrar espacio en el mismo volumen. |
| Reconocimiento de dorsal | RapidOCR con filtros de candidatos y mosaico opcional. | Los mosaicos ayudan cuando un dorsal ocupa poca superficie. La confianza, el recorte y la revisión permiten resolver números de carteles y lecturas dudosas. |
| Ajustes de rango | El rango general o de álbum se aplica al consultar. | Cambiar el rango no obliga a releer fotos. Las decisiones manuales se preservan al reprocesar. |
| Aceleración | CPU como camino base. CUDA y DirectML opcionales cuando están disponibles. | Permite ejecutar en equipos sin GPU compatible. Los tiempos y la calidad de lectura pueden cambiar con el proveedor y el redimensionado. |
| Exportación | Original o ZIP en streaming con `ZIP_STORED`. | Preserva los bytes de origen y evita ensamblar la descarga completa antes de enviarla. |
| Verificación | pytest y Playwright contra un servidor real con biblioteca aislada. | Cubre la lógica y los flujos funcionales sin depender de fotos de carreras privadas. La precisión se mide por separado con etiquetas. |

## Reconocimiento facial

- **Modelos.** YuNet detecta caras y SFace genera vectores. La ruta de CPU usa OpenCV. Las rutas de GPU usan ONNX Runtime cuando es viable. Se descargan los archivos de OpenCV Zoo bajo demanda y se comprueba SHA-256. [Modelos y licencias](../THIRD_PARTY_NOTICES.md)
- **Referencias.** Se proponen caras alineadas con la caja del dorsal y de tamaño y posición plausibles. El análisis de coherencia compara cada cara con las demás cuando hay al menos tres candidatas asociadas. Una lectura dudosa no se preselecciona. La persona usuaria decide qué caras usar.
- **Búsqueda.** Se usa el mayor coseno respecto de las referencias elegidas. El umbral de coincidencia es 0,363 y se indica parecido alto a partir de 0,5. Son puntuaciones de similitud. Los umbrales carecen de calibración con una muestra etiquetada propia.
- **Privacidad.** La función empieza desactivada. El índice vincula vectores a fotos y guarda el consentimiento. El borrado facial retira los datos derivados y limpia el diario de SQLite. [Privacidad y borrado](USER_GUIDE.md)

## Validación pendiente

Las pruebas ejercitan los flujos. Para justificar cambios en filtros, tamaño de entrada, proveedores o umbrales, compara con fotos etiquetadas variadas y un conjunto reservado. Si cambias importación o cola, comprueba interrupciones, reanudación y deduplicación con una biblioteca separada. [Guía de evaluación](EVALUATION.md) · [Informe de validación](VALIDATION_REPORT.md)
