# Operación y diagnóstico

## Arranque y comprobaciones

Ejecuta los comandos desde la raíz del repositorio en PowerShell, después de instalar las dependencias indicadas en el [README](../README.md#primer-arranque-en-windows).

| Comando | Cuándo usarlo |
| --- | --- |
| `pnpm start` | Uso habitual. Compila la interfaz y sirve la aplicación y la API en un solo puerto local. |
| `pnpm run dev` | Desarrollo. Vite sirve la interfaz y reenvía las llamadas a la API. Los cambios en el backend reinician su proceso. |
| `pnpm run dev --network` | Desarrollo o uso controlado desde otro dispositivo de la red local. |
| `pnpm run build` | Compilar la interfaz en `frontend/dist/`. |
| `pnpm test` | Ejecutar las pruebas de Python con el entorno del proyecto ya preparado. |

El puerto de la API empieza en 8000 y el de Vite en 5173. El iniciador elige otro si está ocupado. Copia el puerto de la API que muestra la terminal en esta comprobación.

```powershell
$base = 'http://127.0.0.1:8000'
Invoke-RestMethod "$base/api/health"
```

La respuesta muestra, entre otros campos, `ocr_device`, `face_device` y `workers`. En modo desarrollo puedes usar también la dirección de Vite para consultar la API a través del proxy. [API local](API.md)

## Datos y copias de seguridad

La biblioteca se guarda en `data/` en la raíz del proyecto. Cambia `RACEFINDER_DATA` antes de arrancar para usar otra biblioteca.

```powershell
$env:RACEFINDER_DATA = 'D:\Fotos\RaceFinder-Maraton'
pnpm start
```

| Carpeta o archivo dentro de la biblioteca | Contenido |
| --- | --- |
| `racefinder.sqlite3` y sus archivos auxiliares si existen | Catálogo, álbumes, lecturas, revisiones, favoritos, estado de análisis, ajustes y datos faciales derivados si se ha activado la función. |
| `originals/` | Originales almacenados mediante copia o enlace duro. |
| `thumbs/`, `previews/` y `crops/` | Miniaturas, vistas previas y recortes de dorsales o caras. |
| `tmp/` | Archivos temporales de trabajo. |

Los modelos descargados se guardan por separado en `backend/models/`. Git excluye las bibliotecas y los modelos.

Para hacer una copia, cierra RaceFinder con `Ctrl+C` y espera a que termine el proceso. Copia la **carpeta completa de la biblioteca** a un destino nuevo. Copiar solo SQLite omite las imágenes. Si usaste `RACEFINDER_DATA`, copia esa carpeta en lugar de `data/`.

Para recuperar o trasladar una biblioteca, abre una copia de trabajo de esa carpeta con `RACEFINDER_DATA`. Comprueba que los álbumes y un original se abren antes de sustituir ninguna copia. Para empezar con una biblioteca vacía, apunta la variable a una carpeta nueva.

Una importación por carpeta puede crear un enlace duro que comparte los mismos bytes que el archivo de origen. Si editas el archivo de origen *en el mismo fichero*, la copia de RaceFinder puede reflejar el cambio. Conserva originales sin editar y guarda las ediciones como archivos nuevos. Mantén las copias de bibliotecas con índice facial en un lugar de acceso controlado.

## Actualizar RaceFinder

Si instalaste RaceFinder clonando el repositorio y usas la rama `main`, cierra la aplicación y haz una copia de la biblioteca antes de actualizar. Desde la raíz del proyecto puedes traer los cambios, instalar las dependencias fijadas y arrancar.

```powershell
git pull --ff-only
pnpm install --frozen-lockfile
pnpm start
```

Si usas otra ubicación para los datos, vuelve a establecer `RACEFINDER_DATA` en la terminal antes de arrancar. Conserva la versión anterior de la biblioteca hasta que hayas comprobado la actualización.


## Acceder desde otro dispositivo

1. Ejecuta `pnpm run dev --network` en el ordenador que guarda las fotos.
2. Conecta ambos dispositivos a la misma red de confianza. Abre en el segundo dispositivo la dirección `Network` que muestra Vite.
3. Si Windows pide permiso de firewall, limita el acceso a redes privadas.

El equipo anfitrión procesa las fotos y abre los selectores de carpetas del sistema para importar o guardar. Las descargas por navegador se guardan en el dispositivo que abre la web.

En este modo, cualquier dispositivo que pueda acceder tiene acceso a la biblioteca y sus acciones sin iniciar sesión. Al terminar, cierra RaceFinder. El puerto es para uso local y RaceFinder carece de autenticación para un despliegue público. [Arquitectura y perímetro](ARCHITECTURE.md#perímetro-local)

## Opciones de ejecución

| Variable | Valor inicial | Uso |
| --- | --- | --- |
| `RACEFINDER_DATA` | `data/` en la raíz del proyecto | Seleccionar otra biblioteca. Usa una ruta absoluta para que el resultado no dependa del directorio de trabajo. |
| `RACEFINDER_GPU` | Instalación automática habilitada | `0` desactiva la instalación automática de dependencias de GPU. |
| `RACEFINDER_DEVICE` | `auto` | Dispositivo de OCR. Acepta `auto`, `cpu`, `cuda` o `dml`. |
| `RACEFINDER_FACE_DEVICE` | `auto`, sigue la selección del OCR | Dispositivo facial. Admite las mismas opciones. |
| `RACEFINDER_WORKERS` | Automático | Número de fotos que se analizan en paralelo. El máximo es 16. |
| `RACEFINDER_IMPORT_THREADS` | Hasta 6 según los núcleos disponibles | Hilos de la importación de una carpeta. Acepta entre 1 y 16 tras el ajuste de límites. |
| `RACEFINDER_PRIORITY` | `low` | `normal` mantiene la prioridad normal del proceso. |
| `RACEFINDER_FAST_RESIZE` | `0` | `1` usa OpenCV al reducir imágenes. Puede cambiar lecturas cerca del umbral. Compara antes de usarlo con regularidad. |
| `RACEFINDER_MAX_FILE_MB` y `RACEFINDER_MAX_MEGAPIXELS` | 60 MiB y 100 MP | Límites de tamaño del archivo y de píxeles. |
| `RACEFINDER_DOUBTFUL_BELOW` | `0.85` | Umbral de confianza del OCR por debajo del cual una lectura automática se considera dudosa. |
| `RACEFINDER_API_PORT_START` y `RACEFINDER_NO_OPEN` | `8000` y sin definir | Puerto inicial de la API y opción para arrancar sin abrir el navegador automáticamente, respectivamente. |

### Aceleración por GPU

`pnpm start` y `pnpm run dev` pueden preparar automáticamente ONNX Runtime para una NVIDIA detectada con `nvidia-smi`. Usan las dependencias CUDA 13 cuando el controlador las admite. En Windows, para una NVIDIA con un controlador anterior, el iniciador prueba DirectML. Los paquetes se instalan en `backend/.venv` y su descarga puede ser considerable. RaceFinder intenta volver a CPU si no logra usar el proveedor solicitado.

Para comparar los motores en una carpeta propia después de preparar la GPU, puedes usar esta orden. `--no-faces` mantiene la comparación limitada a dorsales.

```powershell
.\backend\.venv\Scripts\python.exe backend\tools\gpu_bench.py 'D:\Fotos\Maraton' --n 30 --no-faces
```

La instalación manual se detalla en los archivos de requisitos de [CUDA](../backend/requirements-gpu.txt) y [DirectML](../backend/requirements-dml.txt). Para diagnosticar problemas sin cambiar las dependencias instaladas, inicia RaceFinder en CPU explícitamente.

```powershell
$env:RACEFINDER_GPU = '0'
$env:RACEFINDER_DEVICE = 'cpu'
$env:RACEFINDER_FACE_DEVICE = 'cpu'
pnpm start
```

## Solución de problemas

| Síntoma | Qué comprobar |
| --- | --- |
| PowerShell no encuentra `pnpm` o Python | Abre una terminal nueva después de la instalación. Comprueba `node --version`, `pnpm --version` y `py -3.12 --version`. |
| La web dice que RaceFinder no responde | Mantén abierta la terminal y mira la dirección que mostró el iniciador. Consulta `/api/health` y usa **Reintentar** si la API se está reiniciando. |
| El selector **Carpeta** no aparece | Se abre en el equipo que ejecuta RaceFinder y usa `tkinter`. Si no puede abrirse, la importación intenta el selector del navegador. También puedes usar **Añadir fotos** o arrastrar archivos. |
| No sale un dorsal | Espera a que termine el OCR, confirma el álbum correcto y comprueba el rango. Luego prueba **Números parecidos** o revisa las fotos **Sin dorsal leído**. |
| La búsqueda por cara no consigue preparar los modelos | Comprueba que el equipo tiene conexión con OpenCV Zoo y permisos de escritura en `backend/models/`. Revisa el aviso en Ajustes y el registro de la terminal. |
| Hay pocas coincidencias faciales | Espera a que termine el análisis y comprueba las caras de referencia. Gorras, gafas, perfiles o caras pequeñas pueden reducir las coincidencias. |
| La importación se detiene por espacio | Libera espacio en el disco de la biblioteca y repite la importación. RaceFinder rechaza nuevas importaciones si el destino tiene menos de 2 GiB libres. La exportación a carpeta también comprueba el espacio del destino. |
| El motor se queda en CPU o aparece un error de CUDA | Comprueba `ocr_device` y `face_device` en `/api/health` y revisa el registro. Para seguir usando la app, arranca con las variables de CPU que aparecen arriba. |
| Playwright no encuentra Chromium | Instálalo con `pnpm --dir frontend exec playwright install chromium` o usa Edge con `RACEFINDER_E2E_CHANNEL=msedge` en PowerShell mediante `$env:RACEFINDER_E2E_CHANNEL = 'msedge'`. [Pruebas](../CONTRIBUTING.md#verificar-los-cambios) |
| Cambié de carpeta y la biblioteca está vacía | Confirma el valor de `RACEFINDER_DATA` y que la carpeta contiene `racefinder.sqlite3` y `originals/`. RaceFinder inicializa una biblioteca si la ruta no existe. |
