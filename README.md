# RaceFinder

Encuentra tus fotos de una carrera por número de dorsal. Arrastras la carpeta del evento, RaceFinder lee los dorsales en segundo plano y escribes el tuyo: aparecen tus fotos con el dorsal recortado para comprobarlo de un vistazo, listas para descargar en calidad original.

**Todo funciona en tu equipo.** Ninguna foto sale a internet y los originales nunca se modifican.

## Arrancar

Requisitos: Windows 10/11, [Node.js 20+](https://nodejs.org), pnpm y Python 3.10+ (`winget install Python.Python.3.12 --scope user`).

```powershell
pnpm run dev
```

La primera vez crea el entorno de Python e instala todo lo necesario (unos minutos); las siguientes arranca en segundos. Se abre el navegador en `http://127.0.0.1:5173`. Para salir, `Ctrl+C` en la terminal.

Otras órdenes:

| Orden | Para qué |
|---|---|
| `pnpm run dev` | Desarrollo: API + interfaz con recarga automática al guardar (también del backend). |
| `pnpm run dev --network` | Desarrollo con acceso desde otros dispositivos de la red local. |
| `pnpm start` | Uso normal sin recarga: compila la interfaz y la sirve desde la API en un solo puerto. |
| `pnpm test` | Tests del backend. |
| `pnpm --dir frontend exec playwright test` | Pruebas E2E en Chromium (biblioteca aislada). |

### Acceso desde otro dispositivo

Ejecuta `pnpm run dev --network` y abre en el otro dispositivo la dirección que Vite muestra junto a `Network`, por ejemplo `http://192.168.1.25:5173`. Ambos dispositivos deben estar en la misma red local. El puerto empieza en 5173 y se busca el siguiente libre si está ocupado. Si Windows pide permiso para Node.js, permite el acceso en redes privadas.

Usa este modo en una red de confianza. Los dispositivos que puedan conectarse tendrán acceso a la biblioteca y a las acciones de RaceFinder sin iniciar sesión.

El equipo donde ejecutas RaceFinder almacena las fotos y la base de datos, analiza los dorsales y las caras, y prepara las descargas. El otro dispositivo usa sus recursos para mostrar la interfaz, cargar las fotos y guardar los archivos que descargues.

## Cómo se usa

1. **Añade fotos**: pulsa *Carpeta* y elige la carpeta del evento. La lee el propio RaceFinder directamente del disco (no se sube nada por el navegador) y deja cada original como enlace duro, así que **no ocupa espacio extra**; si el disco no lo permite, lo copia. Miles de fotos en pocos minutos, se puede cancelar y las que ya estaban se omiten en un segundo. Arrastrar fotos a la ventana o *Añadir fotos* también funcionan (más lento: pasan por el navegador).
2. **Espera o busca ya**: la barra superior muestra cuántas fotos quedan por leer y el tiempo estimado. Puedes buscar mientras tanto; los resultados se actualizan solos.
3. **Busca tu dorsal**: escribe el número (atajo `/`). Arriba salen las coincidencias seguras; debajo, *Por revisar* (lectura poco clara o un dígito distinto si activas *números parecidos*).
4. **Revisa**: abre una foto para verla en grande, ampliar al 100 % con un clic, confirmar o descartar dorsales y añadir los que falten.
5. **Guarda**: *Guardar las N fotos en una carpeta* abre el selector de carpetas del sistema y copia los originales intactos allí, en una subcarpeta `dorsal-123`, y abre la carpeta. Sin ZIP ni descargas del navegador; no sobrescribe nada. También puedes seleccionar las que quieras (clic en el círculo, `Mayús`+clic para un rango). El ZIP sigue disponible.

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
- **Dorsales de esta carrera**: si conoces el rango (p. ej. 1–2500), se ignoran carteles, años o kilómetros que el lector confunda con dorsales.
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
| `RACEFINDER_WORKERS` | 3 | Fotos analizadas a la vez (dorsales y caras). En una máquina de 16 núcleos, 3 rinde ≈1,3-1,5× lo que 1; con más núcleos prueba 4-6 y mide. |
| `RACEFINDER_IMPORT_THREADS` | 6 | Hilos de la importación de carpetas. |
| `RACEFINDER_DATA` | `./data` | Dónde se guarda la biblioteca. Si la carpeta de fotos está en otro disco, los enlaces duros no son posibles y se copia. |

### GPU para leer dorsales (opcional)

El OCR de dorsales y el reconocimiento facial pueden ir en la GPU (las caras ejecutan los mismos modelos con ONNX Runtime, porque OpenCV 5 ignora la GPU; en CPU siguen usando OpenCV como siempre). Con el `onnxruntime` normal todo va en CPU como siempre. Para activarla, desde la raíz del repositorio (medido en una RTX 5060 Ti: OCR ×2,1 más rápido):

```bash
backend\.venv\Scripts\python.exe -m pip uninstall -y onnxruntime
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-gpu.txt   # CUDA 13 (NVIDIA) con paquetes pip; DirectML: ver el archivo
backend\.venv\Scripts\python.exe backend\tools\gpu_bench.py "RUTA_A_TUS_FOTOS"   # compara CPU y GPU y comprueba que da los mismos dorsales
```

`RACEFINDER_DEVICE=auto|cpu|cuda|dml` (por defecto `auto`: GPU si está disponible); `RACEFINDER_FACE_DEVICE` hace lo mismo solo para las caras (por defecto sigue a la anterior). `/api/health` muestra `ocr_device` y `face_device`. Si la GPU no se puede cargar (faltan CUDA/cuDNN) se avisa en el registro y se usa la CPU. Con GPU, prueba `RACEFINDER_WORKERS` 4-6.

`RACEFINDER_FAST_RESIZE=1` reduce las fotos con `cv2.resize` en vez de PIL Lanczos (3-9× más rápido en esa fase, que con GPU pasa a ser lo que más pesa). Cambia ligeramente los píxeles y puede mover alguna lectura límite, por eso está apagado por defecto: `gpu_bench.py` compara dorsales y caras con y sin él sobre tus fotos para que decidas.

El selector de carpetas usa `tkinter` (en Linux: `sudo apt install python3-tk`). Si no está disponible, *Carpeta* cae al selector del navegador.
