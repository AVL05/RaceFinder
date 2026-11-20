# Contribuir a RaceFinder

Puedes aportar una mejora, corregir un fallo, revisar la documentación o compartir resultados de una evaluación. Abre una incidencia para describir el problema o comentar una propuesta amplia. Las correcciones pequeñas pueden ir directamente en un pull request. [Incidencias de RaceFinder](https://github.com/AVL05/RaceFinder/issues)

## Comunicar un problema

Incluye la versión o el commit, la versión de Windows, los pasos para reproducirlo y los resultados esperado y observado. Si afecta al análisis, indica el modo de OCR, el formato de foto y el dispositivo que devuelve `/api/health`. Para un problema de rendimiento, añade el tamaño de la biblioteca y una medida aproximada.

Usa una imagen sintética o material que tengas permiso para compartir. Antes de publicar un registro o una captura, retira rutas personales, datos privados, originales, bases SQLite y recortes o vectores faciales. Si se trata de un problema de seguridad, pide un canal privado para enviar los detalles sin publicar el procedimiento ni los datos afectados.

## Preparar el entorno

Usa Windows 10 u 11, Node.js 24, Python 3.12 y pnpm 12.16.1, como en la [instalación principal](README.md#primer-arranque-en-windows). Crea un fork en GitHub y sustituye `TU_USUARIO` por tu usuario.

```powershell
git clone https://github.com/TU_USUARIO/RaceFinder.git
Set-Location RaceFinder
git switch -c fix/nombre-del-cambio
pnpm install --frozen-lockfile
$env:RACEFINDER_DATA = Join-Path $env:TEMP ("racefinder-dev-" + [guid]::NewGuid())
$env:RACEFINDER_GPU = '0'
$env:RACEFINDER_DEVICE = 'cpu'
$env:RACEFINDER_FACE_DEVICE = 'cpu'
pnpm run dev
```

Esta sesión usa una biblioteca nueva para que puedas probar importación o borrado con seguridad. Abre la dirección que aparece en la terminal. Cierra el servidor con `Ctrl+C` antes de ejecutar otras comprobaciones en la misma sesión.

## Verificar los cambios

Ejecuta desde la raíz las comprobaciones que correspondan. La primera ejecución de las pruebas de navegador prepara el entorno Python si hace falta. Para ejecutar Python por separado, prepara primero el entorno arrancando RaceFinder al menos una vez.

```powershell
pnpm run build
pnpm test
pnpm --dir frontend exec playwright install chromium
pnpm --dir frontend exec playwright test
git diff --check
```

Para verificar una parte del backend, puedes indicar pytest y el archivo desde la raíz. Este ejemplo ejecuta las pruebas de catálogo.

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_catalog.py
```

Playwright inicia un servidor real en el puerto 8123 con una biblioteca temporal en CPU. La primera ejecución necesita conexión para preparar las imágenes y los modelos de prueba. Puedes usar Microsoft Edge con `$env:RACEFINDER_E2E_CHANNEL = 'msedge'` y omitir la instalación de Chromium. [Configuración E2E](frontend/playwright.config.js) · [Navegadores de Playwright](https://playwright.dev/docs/browsers)

- Para cambios de interfaz, prueba el flujo afectado en escritorio y móvil. Comprueba teclado y foco si cambian los controles.
- Para cambios de catálogo, datos u OCR, verifica con una biblioteca de prueba. Si afecta a persistencia, prueba también tras reiniciar.
- Para cambios de reconocimiento o umbrales, registra versión, equipo, parámetros y muestra. Separa el ajuste de la validación final. [Guía de evaluación](docs/EVALUATION.md)
- Para documentación, revisa enlaces, rutas y ejemplos ejecutables y contrasta los pasos con la interfaz o el comando correspondiente.

## Abrir un pull request

Sube la rama a tu fork y abre un pull request contra `main` de RaceFinder. Explica qué problema resuelve, qué cambia para el usuario y qué comprobaciones ejecutaste. Enlaza la incidencia si existe. Incluye capturas si ayudan a revisar un cambio visual. Mantén fuera del cambio bibliotecas, modelos descargados, capturas de depuración y configuración personal.

Si cambias un flujo visible o un contrato, actualiza también su guía. Usa el repositorio para el código, las instrucciones y los ejemplos reproducibles. Los datos de evaluación permanecen en el equipo de quien los aporta. [Arquitectura](docs/ARCHITECTURE.md) · [Licencia MIT](LICENSE)
