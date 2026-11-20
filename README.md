# RaceFinder

RaceFinder encuentra tus fotos de una carrera por número de dorsal. Importa una carpeta, busca tu número y guarda las fotos originales que quieras. Puedes organizar varias carreras en álbumes, corregir lecturas y, con autorización de las personas correspondientes, buscar fotos adicionales por parecido facial.

Las fotos se procesan en el equipo que ejecuta RaceFinder. La instalación inicial y la primera activación de la búsqueda por cara requieren conexión para descargar sus dependencias o modelos.

## Primer arranque en Windows

La configuración probada en GitHub Actions usa Windows, **Node.js 24**, **Python 3.12** y **pnpm 12.16.1**. Instala Git para clonar el repositorio. En PowerShell puedes instalar Python con `winget install Python.Python.3.12 --scope user` y, una vez instalado Node.js, instalar pnpm con `npm install -g pnpm@12.16.1`. Si acabas de instalar estas herramientas, abre una terminal nueva. [Node.js](https://nodejs.org/en/download) · [Git para Windows](https://git-scm.com/install/windows)

```powershell
git clone https://github.com/AVL05/RaceFinder.git
cd RaceFinder
pnpm install --frozen-lockfile
pnpm start
```

El primer arranque crea el entorno de Python dentro del proyecto. Usa la dirección que aparece en la terminal si el navegador tarda en abrirse. Pulsa `Ctrl+C` en esa terminal para cerrar RaceFinder. Para el primer arranque en CPU, ejecuta `$env:RACEFINDER_GPU = '0'` antes de `pnpm start`. [Arranque, red local y GPU](docs/OPERATIONS.md)

## Encuentra tus fotos

1. Crea un **Nuevo álbum** si quieres separar la carrera de otras. Con el álbum seleccionado, pulsa **Carpeta** o **Añadir fotos**. También puedes arrastrar fotos o carpetas.
2. Escribe tu dorsal y pulsa **Enter**. RaceFinder actualiza los resultados a medida que analiza la biblioteca. Revisa las lecturas dudosas y, si faltan fotos, prueba **Números parecidos**.
3. Selecciona las fotos que quieras. **Guardar selección en carpeta** copia los originales en el equipo que ejecuta RaceFinder. **Descargar selección** entrega el original o un ZIP en el navegador. [Guía de uso completa](docs/USER_GUIDE.md)

## Documentación

| Si quieres… | Consulta |
| --- | --- |
| Encontrar fotos, gestionar álbumes, usar la búsqueda por cara o exportar | [Guía de uso](docs/USER_GUIDE.md) |
| Hacer una copia de seguridad, cambiar de equipo, configurar la GPU o resolver problemas | [Operación y diagnóstico](docs/OPERATIONS.md) |
| Reportar un problema o enviar una mejora | [Guía de contribución](CONTRIBUTING.md) |
| Entender el servidor, la base de datos y la interfaz | [Arquitectura](docs/ARCHITECTURE.md), [API local](docs/API.md) y [decisiones técnicas](docs/TECHNICAL_DECISIONS.md) |
| Medir la búsqueda con tus propias fotos y consultar la evidencia disponible | [Evaluación](docs/EVALUATION.md) e [informe de validación](docs/VALIDATION_REPORT.md) |
| Mantener el diseño o proponer una mejora del producto | [Diseño de interfaz](design.md) y [hoja de ruta](docs/ROADMAP.md) |

El código de RaceFinder usa la licencia MIT. Los modelos y las dependencias conservan sus propias licencias. [Licencia](LICENSE) · [Avisos de terceros](THIRD_PARTY_NOTICES.md)
