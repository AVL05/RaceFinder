# Evaluación de dorsales y búsqueda por cara

Esta guía explica cómo medir RaceFinder con fotos etiquetadas localmente. Usa fotos que tengas permiso para procesar. Para medir la búsqueda facial, confirma también que tienes permiso para ese análisis. Mantén las fotos, etiquetas y bibliotecas fuera de Git.

## Preparar la muestra

Incluye fotos con dorsales legibles, fotos con corredores sin dorsal legible y fotos sin dorsales, como público o carteles. Varía el tamaño, la luz, el ángulo y el número de corredores. Etiqueta antes de mirar el resultado del OCR para reducir el sesgo. Para comparar resultados, registra la versión, el modo, el dispositivo, el equipo y cuántas fotos hay en cada partición.

Cada foto se asigna de forma determinista según su SHA-256. Aproximadamente el 30 % va a `tune` y el 70 % a `test`. Ajusta con `tune`, fija los parámetros y después usa `test` como validación final. La proporción efectiva puede variar en muestras pequeñas. Las fotos casi idénticas de una ráfaga pueden caer en particiones distintas. Para una comparación más exigente, reserva otra carrera o sesión completa y evalúala por separado.

## Evaluar una carpeta desde PowerShell

Desde la raíz del repositorio, con `backend/.venv` preparado por el [primer arranque](../README.md#primer-arranque-en-windows), crea la plantilla en la carpeta de las fotos. El comando preserva una plantilla existente.

```powershell
.\backend\.venv\Scripts\python.exe backend\tools\eval_folder.py plantilla 'D:\Fotos\Maraton'
```

Abre `racefinder-etiquetas.json`. Las claves son rutas relativas con `/` y la extensión original. El comando recorre subcarpetas e incluye JPG, JPEG, PNG y WebP.

```json
{
  "meta/IMG_0012.jpg": {
    "bibs": ["184"],
    "present": ["77"],
    "tags": ["varios_corredores", "gorra"]
  },
  "IMG_0100.jpg": {
    "bibs": [],
    "present": [],
    "tags": ["cartel_reloj"]
  }
}
```

- `bibs` contiene los dorsales que puedes leer con seguridad. Escríbelos como cadenas para conservar ceros iniciales.
- `present` contiene dorsales de corredores identificados con certeza por otra evidencia cuando su dorsal no se lee en esa foto.
- `tags` es opcional. Usa `inclinado`, `ocluido`, `pequeno`, `varios_corredores`, `fondo_complejo`, `cartel_reloj`, `poca_luz`, `desenfocado`, `cara_pequena`, `perfil`, `gafas` o `gorra`.
- Elimina del JSON las entradas sin revisar. Una entrada con las dos listas vacías se evalúa como ejemplo negativo. Si hay archivos idénticos byte a byte, deja una sola entrada por original.

Ejecuta la evaluación con un destino nuevo para separar la biblioteca de ensayo de tu biblioteca habitual.

```powershell
.\backend\.venv\Scripts\python.exe backend\tools\eval_folder.py evaluar 'D:\Fotos\Maraton' --datos 'D:\Evaluaciones\Maraton-01'
```

Para incluir caras, añade `--caras --consiento` a la orden anterior y usa un destino propio para esa evaluación. Los modelos pueden descargarse en el primer uso. Si omites `--datos`, se crea una biblioteca bajo `data_eval/`. Usa destinos distintos para comparar configuraciones desde cero. Reutilizar el destino reemplaza sus etiquetas de evaluación y puede aprovechar análisis previos. Los tiempos del CLI reflejan las fotos procesadas en esa ejecución.

El destino contiene `informe-evaluacion.md` e `informe-evaluacion.json`. El JSON añade datos por partición, modo, condición y ejemplos de errores de búsqueda. Puedes abrir la biblioteca generada con `RACEFINDER_DATA` para revisar resultados. [Operación y bibliotecas](OPERATIONS.md#datos-y-copias-de-seguridad)

## Evaluar en la interfaz

1. Abre **Ajustes → Medir la precisión (avanzado)** en una biblioteca de prueba.
2. Etiqueta cada foto con sus dorsales visibles o indica que el dorsal es ilegible. Si sabes qué corredor aparece, registra también su dorsal en **Corredores sin dorsal legible**. Puedes añadir etiquetas de dificultad.
3. Espera a que termine el análisis normal. Selecciona `tune` y pulsa **Evaluar OCR** para comparar lecturas contra etiquetas. Los parámetros de esta prueba se aplican a esa ejecución.
4. Usa **Evaluar búsqueda (dorsal + cara)** para medir con el índice de la biblioteca. Para incluir caras, actívalas con permiso y espera a que termine su análisis.
5. Cuando hayas fijado los parámetros, selecciona `test` y confirma la ejecución final.

La interfaz guarda las ejecuciones en la biblioteca. **Evaluar OCR** vuelve a leer las fotos etiquetadas y recoge tiempos. **Evaluar búsqueda** reutiliza las lecturas y caras ya indexadas. Mide la búsqueda exacta y la selección automática de referencias, sin reproducir los filtros de álbum ni los cambios de referencias que haga el usuario en la interfaz.

## Interpretar el informe

| Qué se mide | Unidad y lectura |
| --- | --- |
| OCR | Cada par foto–dorsal legible es una instancia. Un falso positivo es un número leído sin etiqueta y un falso negativo es un número etiquetado que falta. Se informa también por foto y por condición. |
| Búsqueda | Por cada dorsal legible en la partición, se comparan las fotos encontradas con las fotos etiquetadas donde aparece el corredor. Incluye apariciones registradas en `present`. Con caras, se informa por dorsal, cara y unión de ambos. |
| Aporte de la cara | Proporción de apariciones sin dorsal legible recuperadas por cara. Se mide la recuperación de fotos, de forma indirecta respecto a la asociación cara–dorsal. |
| Tiempos | Dependen de equipo, dispositivo, modos, resolución y calentamiento de los modelos. En comparaciones de CLI, revisa el número de fotos efectivamente procesadas. |

La precisión divide aciertos por resultados devueltos. La exhaustividad (*recall*) divide aciertos por resultados esperados. F1 resume ambas. Un campo sin denominador aparece vacío. Comparte el número de fotos y errores junto a las tasas, especialmente en muestras pequeñas.

Si vas a compartir un informe, revisa la ruta de origen y los identificadores que aparecen en él. Publica resultados agregados y usa material autorizado para ilustrar fallos. [Estado de la validación](VALIDATION_REPORT.md)
