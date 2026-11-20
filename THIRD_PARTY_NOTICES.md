# Avisos de terceros

El código de RaceFinder se publica bajo MIT. Los modelos, recursos y dependencias conservan sus licencias. RaceFinder descarga los modelos faciales de OpenCV Zoo cuando se necesitan y verifica su SHA-256. Si distribuyes los modelos o paquetes de terceros, conserva los avisos y textos requeridos por sus licencias. [Licencia de RaceFinder](LICENSE) · [Descarga y hashes](backend/app/faces.py)

## Modelos de reconocimiento facial

| Modelo | Archivo | Tamaño | SHA-256 | Licencia | Origen |
|---|---|---|---|---|---|
| YuNet (detección de caras) | `face_detection_yunet_2026may.onnx` | 229 738 B | `ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0` | MIT | [opencv_zoo/models/face_detection_yunet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) |
| SFace (vector facial, MobileFaceNet) | `face_recognition_sface_2021dec.onnx` | 38 696 353 B | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` | Apache-2.0 | [opencv_zoo/models/face_recognition_sface](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) |

Los textos de las licencias están en OpenCV Zoo. [YuNet (MIT)](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/LICENSE) · [SFace (Apache-2.0)](https://github.com/opencv/opencv_zoo/blob/main/models/face_recognition_sface/LICENSE)

- `face_detection_yunet_2026may.onnx` es, según OpenCV Zoo, la re-exportación de `face_detection_yunet_2023mar.onnx` con entrada dinámica, el modelo recomendado para OpenCV 5.x. Antes de cambiarlo, se comprobó en OpenCV 5.0.0 que ambos dan exactamente las mismas detecciones: mismo número de caras e IoU medio 1,0 en 2 imágenes oficiales de OpenCV (`messi5.jpg` y `example_outputs/largest_selfie.jpg` de OpenCV Zoo, entre 42 y 122 caras), cada una a 3 escalas.
- **YuNet.** Shiqi Yu y colaboradores. W. Wu, H. Peng y S. Yu, *YuNet: A Tiny Millisecond-level Face Detector*, Machine Intelligence Research, 2023. [Código original](https://github.com/ShiqiYu/libfacedetection.train)
- **SFace.** Yaoyao Zhong y colaboradores, *SFace: Sigmoid-Constrained Hypersphere Loss for Robust Face Recognition*. Conversión a ONNX de Chengrui Wang. [Artículo](https://arxiv.org/abs/2205.12010) · [Código original](https://github.com/zhongyy/SFace)
- El umbral de coincidencia de 0,363 (coseno) es el que publica OpenCV para SFace en `samples/dnn/face_detect.py`. No se ha recalibrado con datos propios.

### Texto de la licencia MIT de YuNet

```
MIT License

Copyright (c) 2020 Shiqi Yu <shiqi.yu@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

SFace mantiene su texto de licencia de Apache 2.0. [Texto completo](https://www.apache.org/licenses/LICENSE-2.0)

## OCR
RaceFinder usa `rapidocr-onnxruntime` 1.4.4 (Apache-2.0) y los modelos PP-OCR que distribuye el paquete. [RapidOCR](https://github.com/RapidAI/RapidOCR) · [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)

## Bibliotecas
OpenCV (Apache-2.0), ONNX Runtime (MIT), FastAPI (MIT), Uvicorn (BSD-3-Clause), Pillow (MIT-CMU/HPND), NumPy (BSD-3-Clause), React (MIT), Vite (MIT), Tailwind CSS (MIT), Lucide (ISC y MIT para iconos derivados de Feather), Playwright (Apache-2.0, solo para pruebas). [Licencia y atribuciones de Lucide](https://github.com/lucide-icons/lucide/blob/main/LICENSE)

## Imágenes de demostración y prueba
La foto de ejemplo de la interfaz fue generada para RaceFinder y se conserva en dos tamaños en `frontend/public/`. Las pruebas de navegador descargan `messi5.jpg` y `lena.jpg` de `opencv/opencv/samples/data` para generar fixtures funcionales. Esos archivos se descargan fuera del contenido versionado. [Preparación de fixtures](frontend/e2e/global-setup.js) · [Imágenes de ejemplo de OpenCV](https://github.com/opencv/opencv/tree/main/samples/data)
