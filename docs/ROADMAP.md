# Roadmap

## Fase 0 — Investigación y arquitectura ✅
Entorno inspeccionado, decisiones y riesgos documentados.

## Fase 1 — MVP ✅ (con limitaciones de validación)
Importación, miniaturas, galería, OCR real, búsqueda por dorsal, revisión manual, exportación, tests.

## Antes de Fase 2 (validación)
- Reunir un conjunto de evaluación etiquetado (ver EVALUATION.md) y medir precisión/recall del OCR en fotos reales.
- Ajustar umbrales (`min_conf`, tamaño mínimo de caja) con datos.
- Prueba de carga con ≥1 000 fotos reales.

## Fase 2 — Reconocimiento facial (no iniciada)
Referencias autorizadas con consentimiento, detección + embeddings ONNX, similitud (sin presentarla como probabilidad), borrado de biometría, búsqueda combinada con evidencia por método. Resolver licencia de modelos primero.

## Fase 3 — Optimización y distribución
GPU opcional (onnxruntime-gpu), indexación in situ sin copiar, detector de personas/dorsal, empaquetado, autenticación si deja de ser solo local.
