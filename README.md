# RaceFinder

Encuentra tus fotos de una carrera por número de dorsal. Arrastras la carpeta del evento, RaceFinder lee los dorsales en segundo plano y escribes el tuyo: aparecen tus fotos con el dorsal recortado para comprobarlo de un vistazo, listas para descargar en calidad original.

**Todo funciona en tu equipo.** Ninguna foto sale a internet y los originales nunca se modifican.

## Arrancar

Requisitos recomendados para Windows 10/11: Node.js 24, Python 3.12 y pnpm 12.16.1. El proyecto admite Node.js 20.19+ dentro de la rama 20 y versiones desde 22.12. Puedes instalar Python con `winget install Python.Python.3.12 --scope user` y pnpm con `npm install -g pnpm@12.16.1`.

```powershell
git clone https://github.com/AVL05/RaceFinder.git
cd RaceFinder
pnpm install --frozen-lockfile
pnpm start
```

La primera vez RaceFinder prepara el entorno de Python. Abre la dirección local que muestra la terminal si el navegador no se abre automáticamente. Para salir, pulsa `Ctrl+C` en la terminal. Si quieres arrancar por primera vez sin instalar los paquetes opcionales de GPU, ejecuta `$env:RACEFINDER_GPU = '0'` antes de `pnpm start`.

Otras órdenes:

| Orden | Para qué |
|---|---|
| `pnpm run dev` | Desarrollo: API + interfaz con recarga automática al guardar (también del backend). |
| `pnpm run dev --network` | Desarrollo con acceso desde otros dispositivos de la red local. |
| `pnpm start` | Uso normal sin recarga: compila la interfaz y la sirve desde la API en un solo puerto. |
| `pnpm test` | Tests del backend. |
| `pnpm --dir frontend exec playwright test` | Pruebas E2E en una biblioteca aislada. Instala Chromium con `pnpm --dir frontend exec playwright install chromium` antes de la primera ejecución. |

### Acceso desde otro dispositivo

Ejecuta `pnpm run dev --network` y abre en el otro dispositivo la dirección que Vite muestra junto a `Network`, por ejemplo `http://192.168.1.25:5173`. Ambos dispositivos deben estar en la misma red local. El puerto empieza en 5173 y se busca el siguiente libre si está ocupado. Si Windows pide permiso para Node.js, permite el acceso en redes privadas.

Usa este modo en una red de confianza. Los dispositivos que puedan conectarse tendrán acceso a la biblioteca y a las acciones de RaceFinder sin iniciar sesión.

El equipo donde ejecutas RaceFinder almacena las fotos y la base de datos, analiza los dorsales y las caras, y prepara las descargas. El otro dispositivo usa sus recursos para mostrar la interfaz, cargar las fotos y guardar los archivos que descargues.

## Cómo se usa

1. **Añade fotos**: pulsa *Carpeta* y elige la carpeta del evento. La lee el propio RaceFinder directamente del disco (no se sube nada por el navegador) y deja cada original como enlace duro, así que **no ocupa espacio extra**; si el disco no lo permite, lo copia. Miles de fotos en pocos minutos, se puede cancelar y las que ya estaban se omiten en un segundo. Arrastrar fotos a la ventana o *Añadir fotos* también funcionan (más lento: pasan por el navegador).
2. **Espera o busca ya**: la barra superior muestra cuántas fotos quedan por leer y el tiempo estimado. Puedes buscar mientras tanto; los resultados se actualizan solos.
3. **Busca tu dorsal**: escribe el número (atajo `/`). Arriba salen las coincidencias seguras; debajo, *Por revisar* (lectura poco clara o un dígito distinto si activas *números parecidos*).
4. **Revisa**: abre una foto para verla en grande, ampliar al 100 % con un clic, confirmar o descartar dorsales y añadir los que falten.
5. **Guarda**: *Guardar N fotos* abre el selector de carpetas del sistema y copia los originales intactos a una subcarpeta `dorsal-123`. Puedes seleccionar fotos concretas con el círculo de cada miniatura, extender la selección con `Mayús`+clic o descargar los originales como ZIP.

### Organizar varias carreras

1. Pulsa **Nuevo álbum** y, si conoces los dorsales válidos de esa carrera, indica su rango. Puedes cambiarlo después desde **Editar álbum**.
2. Con el álbum seleccionado, importa la carpeta o añade las fotos. Si ya estaban en RaceFinder, selecciona las que quieras en **Toda la biblioteca** y usa **Organizar selección en álbumes**. Una foto puede estar en varios álbumes y se almacena una sola vez.
3. Busca el dorsal dentro del álbum. El índice, los resultados por dorsal y la búsqueda por cara usan el álbum activo. Puedes guardar la dirección del navegador para volver a ese álbum y dorsal en esta instalación.

Al quitar fotos de un álbum o eliminar el álbum, las fotos siguen disponibles en la biblioteca. **Quitar de RaceFinder** elimina del catálogo la foto y sus pertenencias en todos los álbumes.

### Buscar, revisar y preparar la entrega

- **Nombre de archivo y orden**. Localiza un archivo y ordena por fecha de importación o por nombre.
- **Favoritas**. Usa la estrella de una miniatura, del visor o de la selección para guardar tus favoritas y volver a ellas con su filtro.
- **Por revisar**. Reúne fotos con un dorsal automático de baja confianza. En el visor puedes confirmar o descartar la lectura y añadir dorsales que falten.
- **Selección completa**. *Seleccionar todas* en la galería incluye las fotos de todo el filtro, también las que aún no se han cargado en pantalla. Admite hasta 20.000 fotos por selección.
- **Catálogo CSV**. Descarga una fila por foto del filtro activo, con el nombre de archivo, el álbum activo, los dorsales, la marca de favorita, el estado de análisis y la fecha de importación UTC.

### Búsqueda por cara (opcional)

Bajo los resultados de un dorsal aparece *Buscar también por la cara*. Tras aceptar el aviso de privacidad:

1. RaceFinder analiza las caras de todas las fotos en segundo plano (la primera vez descarga los modelos de OpenCV, 38 MB).
2. En *Tu cara en otras fotos* propone las caras que aparecen justo encima de tu dorsal. Desmarca las que no sean tuyas.
3. Debajo salen las fotos **donde no se lee el dorsal pero aparece una cara parecida**, y las fotos del dorsal en las que también coincide la cara se marcan como *Dorsal + cara*.

El parecido facial no es una certeza: revisa las fotos antes de descargarlas. Los datos faciales son vectores anónimos que solo están en tu equipo; se borran todos desde *Ajustes → Búsqueda por cara*.

En la portada tienes la lista de **dorsales encontrados** para explorar sin buscar, y filtros (*con dorsal*, *sin dorsal leído*…).

Atajos en el visor: `←` `→` navegar · `S` seleccionar · `Z` o clic ampliar · `B` marcas del dorsal · `D` descargar · `Esc` cerrar.

### Ajustes

- **Lectura de dorsales**: *Rápido*, *Equilibrado* (recomendado) o *A fondo* (para fotos con mucha gente lejos; más lento).
- **Rango global de dorsales**. Se usa en toda la biblioteca y en los álbumes que no tienen rango propio. Las correcciones manuales se conservan fuera del rango.
- **Volver a leer todas las fotos** tras cambiar el modo. Tus correcciones manuales se conservan.
- **Eliminar todas las fotos**: vacía la biblioteca de una vez (copias, miniaturas, dorsales, datos faciales y etiquetas). Pide escribir `ELIMINAR`. Tus archivos originales en el disco y los ajustes no se tocan.

## Datos

Todo se guarda en `data/` (originales, miniaturas y base de datos SQLite). Para empezar de cero, cierra RaceFinder y borra esa carpeta. Para usar otra carpeta: `$env:RACEFINDER_DATA="D:\fotos-maraton"; pnpm run dev`.

La API solo escucha en `127.0.0.1`, no envía telemetría y valida cada archivo por su contenido.

## Cómo funciona

- **Backend**: Python + FastAPI + SQLite. Una cola persistente lee los dorsales con RapidOCR (modelos PP-OCR en ONNX, CPU): detecta zonas de texto, descarta las que no pueden ser un dorsal y reconoce el resto en lote. Si se cierra a medias, continúa al volver a arrancar.
- **Frontend**: React + Vite + Tailwind, en JavaScript.
- **Caras** (opcional): OpenCV YuNet + SFace (licencias MIT / Apache-2.0), en CPU.

Más detalle en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/TECHNICAL_DECISIONS.md](docs/TECHNICAL_DECISIONS.md), [docs/VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md) y [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

**Medir la precisión con tus fotos**: [docs/EVALUATION.md](docs/EVALUATION.md) (todavía no hay métricas con fotos reales).

## Usarlo en otro ordenador (más potente)

```bash
git clone <este repositorio>
cd RaceFinder
pnpm install
pnpm run start        # o pnpm run dev
```

La biblioteca (`data/`) no está en el repositorio: se crea vacía en cada equipo, y los modelos faciales se descargan la primera vez. Para repartir el trabajo con más núcleos:

| Variable | Por defecto | Para qué |
|---|---|---|
| `RACEFINDER_WORKERS` | automático | Fotos analizadas a la vez (dorsales y caras). Por defecto se calcula según tus núcleos, tu RAM y si hay GPU (portátil de 16 hilos y 16 GB con GPU: 5; solo CPU: 2-3). Forzar un número (máx. 16) solo si mides que mejora; demasiados saturan CPU y RAM. |
| `RACEFINDER_PRIORITY` | `low` | El análisis corre con prioridad algo menor para que el equipo siga ágil mientras trabaja. `normal` lo desactiva. |
| `RACEFINDER_IMPORT_THREADS` | 6 | Hilos de la importación de carpetas. |
| `RACEFINDER_DATA` | `./data` | Dónde se guarda la biblioteca. Si la carpeta de fotos está en otro disco, los enlaces duros no son posibles y se copia. |

### GPU para leer dorsales (automática)

`pnpm run dev` detecta una GPU NVIDIA (con `nvidia-smi`) y, la primera vez, cambia en `backend/.venv` el `onnxruntime` de CPU por el de GPU (descarga de unos GB; no instala nada fuera del proyecto). Con driver CUDA 13 usa `requirements-gpu.txt`; con un driver NVIDIA más antiguo, en Windows usa DirectML (`requirements-dml.txt`). Si falla, sigue en CPU. Desactivar con `RACEFINDER_GPU=0`. Lo que sigue es la instalación manual y los detalles.

El OCR de dorsales y el reconocimiento facial pueden ir en la GPU (las caras ejecutan los mismos modelos con ONNX Runtime, porque OpenCV 5 ignora la GPU; en CPU siguen usando OpenCV como siempre). Con el `onnxruntime` normal todo va en CPU como siempre. Para activarla, desde la raíz del repositorio (medido en una RTX 5060 Ti: OCR ×2,1 más rápido):

```bash
backend\.venv\Scripts\python.exe -m pip uninstall -y onnxruntime
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-gpu.txt   # CUDA 13 (NVIDIA) con paquetes pip; DirectML: ver el archivo
backend\.venv\Scripts\python.exe backend\tools\gpu_bench.py "RUTA_A_TUS_FOTOS"   # compara CPU y GPU y comprueba que da los mismos dorsales
```

`RACEFINDER_DEVICE=auto|cpu|cuda|dml` (por defecto `auto`: GPU si está disponible); `RACEFINDER_FACE_DEVICE` hace lo mismo solo para las caras (por defecto sigue a la anterior). `/api/health` muestra `ocr_device` y `face_device`. Si la GPU no se puede cargar (faltan CUDA/cuDNN) se avisa en el registro y se usa la CPU. `/api/health` también muestra `workers`.

`RACEFINDER_FAST_RESIZE=1` reduce las fotos con `cv2.resize` en vez de PIL Lanczos (3-9× más rápido en esa fase, que con GPU pasa a ser lo que más pesa). Cambia ligeramente los píxeles y puede mover alguna lectura límite, por eso está apagado por defecto: `gpu_bench.py` compara dorsales y caras con y sin él sobre tus fotos para que decidas.

El selector de carpetas usa `tkinter` (en Linux: `sudo apt install python3-tk`). Si no está disponible, *Carpeta* cae al selector del navegador.

## Contribuir

Puedes reportar un problema, proponer una mejora o enviar un pull request desde tu fork. [Incidencias de RaceFinder](https://github.com/AVL05/RaceFinder/issues) · [Guía de contribución](CONTRIBUTING.md)

El código de RaceFinder usa la licencia MIT. Los componentes de terceros tienen sus propios avisos. [Licencia de RaceFinder](LICENSE) · [Avisos de terceros](THIRD_PARTY_NOTICES.md)
