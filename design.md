# Diseño de RaceFinder

## Mantener la interfaz

RaceFinder prioriza tres tareas según el estado de la biblioteca. En una biblioteca vacía, el primer paso es la importación. Con fotos importadas, la galería, los álbumes y el índice permiten elegir el conjunto que se va a revisar. En resultados, el dorsal, sus evidencias y el acceso al original orientan la selección y la exportación. [Guía de uso](docs/USER_GUIDE.md)

- Mantén claras las acciones disponibles en la biblioteca global y en un álbum activo. Conserva el contexto del álbum al buscar, filtrar y retroceder.
- Distingue coincidencia segura, lectura dudosa y parecido facial con texto y jerarquía visual. Usa el recorte o las marcas como evidencia que se pueda revisar.
- Conserva los nombres accesibles, el foco visible y los atajos del visor. Comprueba los estados de carga, error, vacío y selección con teclado y a ancho móvil.
- Usa los estilos de `frontend/src/index.css` y componentes existentes del catálogo, álbumes y visor antes de añadir variantes. [Estilos](frontend/src/index.css) · [Arquitectura](docs/ARCHITECTURE.md)

## Dirección visual

RaceFinder funciona como una mesa de edición deportiva donde el dorsal abre paso a las fotos originales.

El público son corredores y fotógrafos que necesitan localizar, revisar y guardar imágenes de una carrera en su equipo. La prioridad de la biblioteca vacía es importar una carpeta. Con fotos disponibles, las prioridades son buscar por dorsal, explorar el índice y pasar de la galería al visor.

| Dirección | Experiencia y decisión |
| --- | --- |
| Mesa de edición deportiva | Portada partida entre ficha de importación y foto de ejemplo. Con fotos, el índice lleva a una ficha con el dorsal ampliado y sus coincidencias. Es la dirección elegida porque une el contexto deportivo con la tarea diaria. |
| Hoja de contactos | La portada abre con una cuadrícula continua de imágenes y deja el índice en segundo plano. Favorece el recorrido visual de un fotógrafo, con menos orientación para quien todavía debe importar fotos. |
| Cronometraje | La portada sigue la secuencia importar, analizar y encontrar, con estados y cifras en primer plano. Ayuda durante un análisis largo, con más densidad que la necesaria para recorrer una biblioteca ya procesada. |

El gesto distintivo es elegir un dorsal del índice y verlo ampliado como ficha de resultados, con la búsqueda conservada en la URL. El corte de lectura sobre el dorsal de la foto ilustrativa anticipa ese gesto en la biblioteca vacía.

## Sistema

- Tipografía de sistema Segoe UI con alternativas locales. Números tabulares en dorsales y contadores, y monoespaciada en etiquetas cortas. Sin descargas de fuentes.
- Carbón cálido para el espacio de trabajo, marfil para la ficha de importación y naranja para el foco y las acciones principales. Texto secundario con objetivo de contraste 4,5:1 en su superficie.
- Contenedor de hasta 1.536 px con márgenes fluidos. Una columna en móvil y portada partida desde 880 px. La galería mantiene dos columnas en móvil y calcula las demás según el ancho disponible.
- Bordes finos, controles con altura mínima de 44 px en las acciones principales y foco visible. El visor conserva un fondo oscuro para revisar la imagen y muestra sus controles de navegación en pantallas táctiles.
- Fotografía ilustrativa original generada con IA para la biblioteca vacía. WebP locales de 720 y 1.280 px. La galería y el visor usan las imágenes de la biblioteca.
- Movimiento breve en la entrada de la ficha y en los cambios de foco visual. Se respeta la preferencia de movimiento reducido.

## Criterios de aceptación

La portada muestra importación, ejemplo y privacidad. El índice lleva al dorsal correcto con teclado y ratón. Los resultados distinguen coincidencias seguras, dudosas y faciales. El encabezado permite importar y controlar el análisis en móvil. Filtros, selección, visor, configuración y exportación conservan sus flujos. Para revisar un cambio que afecte a la composición, comprueba los estados afectados a 375, 768, 1.440 y 1.920 px.

## Verificación histórica del rediseño inicial

| Control | Resultado | Evidencia |
| --- | --- | --- |
| G1 Dirección | PASS | Se evaluaron tres composiciones y se eligió la mesa de edición deportiva. |
| G2 Sistema | PASS | Los componentes principales comparten tipografía, color, contenedor, controles y estados de foco. |
| G3 Revisión visual | PASS | Playwright con Microsoft Edge a 375 × 812, 768 × 1.024, 1.440 × 900 y 1.920 × 1.080. |
| G4 Interacciones | PASS | Atajo de búsqueda, activación del dorsal con Enter, filtros con flechas, selección, navegación del visor, borrado de la búsqueda y apertura y cierre de Ajustes. Pausa y reanudación verificadas en móvil con respuestas simuladas. |
| G5 Adaptación | PASS | Portada, galería, resultados, visor, selección y Ajustes sin desplazamiento horizontal de página en los cuatro anchos. Se corrigió y comprobó también el ancho interno de Ajustes. |
| G6 Accesibilidad | PASS | Foco visible y devolución del foco, nombres de controles, pestañas y preferencia de movimiento reducido comprobados. El texto secundario tiene un contraste de 6,39:1 sobre el panel oscuro y 6,82:1 sobre el marfil. Revisión acotada a estos estados y a Edge. |
| G7 Ingeniería | PASS | `pnpm run build` y `git diff --check`. `pnpm test` dio 102 pruebas correctas con `CUDA_VISIBLE_DEVICES=-1` para reproducir el entorno sin CUDA que presupone la prueba de retorno a CPU. |
| G8 Peso de recursos | PASS | Vite midió 96,73 kB gzip de JS y 9,70 kB gzip de CSS. La foto pesa 34.402 o 73.932 bytes según el tamaño y Edge cargó la variante esperada. Lighthouse y métricas de campo **NOT RUN**. |
| G9 Imágenes | PASS | Imagen ilustrativa generada para RaceFinder, identificada en la interfaz, con texto alternativo y dimensiones reservadas. |
| G10 Regresión | PASS | 7 pruebas E2E con la API real, en una biblioteca aislada con rango de dorsales 1–1.000. Se probó importación, revisión, consentimiento, búsqueda facial, etiquetado y borrado. El selector nativo de Windows no se automatizó. |
| G11 Ambición visual | PASS | El prototipo se revisó antes de extenderlo a la galería y al visor. La portada pasó de un cuadro centrado a una composición con fotografía, importación y datos locales. Seleccionar el 184 con Enter lleva a la ficha ampliada y conserva `?dorsal=184` en la URL. |

Las capturas de la revisión se guardaron como archivos locales. Las instrucciones para comprobar la versión actual están en la [guía de contribución](CONTRIBUTING.md).

Se aplicaron `design-taste-frontend` a la composición, `ui-ux-pro-max` a la exploración de estilo, `impeccable` al acabado sobre capturas reales y `web-design-guidelines` a la revisión de controles. [Guía de interfaces web](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md)
