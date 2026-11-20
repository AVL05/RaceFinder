# Contribuir a RaceFinder

Abre una incidencia si tienes un caso que RaceFinder no cubre o un fallo reproducible. Indica la versión de Windows, qué estabas haciendo, el resultado esperado y el observado. Para adjuntar capturas o imágenes, usa ejemplos sintéticos o material que puedas compartir. Omite rutas personales, fotos privadas y archivos de la biblioteca.

## Preparar el entorno

Usa Windows 10/11, Node.js 24, Python 3.12 y pnpm 12.16.1. Haz un fork, clona tu copia y crea una rama para el cambio.

```powershell
git switch -c fix/nombre-del-cambio
pnpm install --frozen-lockfile
$env:RACEFINDER_GPU = '0'
pnpm run dev
```

RaceFinder abre una dirección en localhost y guarda los datos en `data/`. Si necesitas probar con otra biblioteca, configura `RACEFINDER_DATA` con una ruta diferente antes de arrancar.

## Verificar y enviar

```powershell
pnpm run build
pnpm --dir frontend exec playwright install chromium
pnpm --dir frontend exec playwright test
pnpm test
```

Las pruebas de navegador crean una biblioteca temporal y preparan las imágenes y modelos de prueba. La primera ejecución necesita conexión para descargar estos recursos. Si ya tienes Microsoft Edge, puedes usarlo con `$env:RACEFINDER_E2E_CHANNEL = 'msedge'` y omitir la instalación de Chromium. [Navegadores de Playwright](https://playwright.dev/docs/browsers)

Abre un pull request con el problema que resuelves, qué cambió y cómo lo comprobaste. Si una prueba necesita imágenes, usa datos sintéticos pequeños. Mantén fuera del commit `data/`, los modelos descargados, las capturas locales y la configuración de tus herramientas.
