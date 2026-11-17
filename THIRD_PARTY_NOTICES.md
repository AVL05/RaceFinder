# Avisos de terceros

RaceFinder usa los siguientes modelos y bibliotecas. Los modelos faciales no se incluyen en el repositorio: se descargan del repositorio oficial de OpenCV Zoo la primera vez que el usuario activa la búsqueda por cara y se verifica su SHA-256 (`backend/app/faces.py`). Si se distribuye RaceFinder con los modelos incluidos, este archivo debe acompañarlos.

## Modelos de reconocimiento facial (verificado el 16-11-2026)

| Modelo | Archivo | Tamaño | SHA-256 | Licencia | Origen |
|---|---|---|---|---|---|
| YuNet (detección de caras) | `face_detection_yunet_2026may.onnx` | 229 738 B | `ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0` | MIT | [opencv_zoo/models/face_detection_yunet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) |
| SFace (vector facial, MobileFaceNet) | `face_recognition_sface_2021dec.onnx` | 38 696 353 B | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` | Apache-2.0 | [opencv_zoo/models/face_recognition_sface](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) |

Las licencias se han leído en los archivos `LICENSE` de cada carpeta del repositorio oficial (*"All files in this directory are licensed under …"*, según su README).

- `face_detection_yunet_2026may.onnx` es, según OpenCV Zoo, la re-exportación de `face_detection_yunet_2023mar.onnx` con entrada dinámica, el modelo recomendado para OpenCV 5.x. Antes de cambiarlo, se comprobó en OpenCV 5.0.0 que ambos dan exactamente las mismas detecciones: mismo número de caras e IoU medio 1,0 en 2 imágenes oficiales de OpenCV (`messi5.jpg` y `example_outputs/largest_selfie.jpg` de OpenCV Zoo, entre 42 y 122 caras), cada una a 3 escalas.
- Atribución de YuNet: Shiqi Yu y colaboradores. Wu, W., Peng, H., Yu, S. *YuNet: A Tiny Millisecond-level Face Detector*, Machine Intelligence Research, 2023. Código original: https://github.com/ShiqiYu/libfacedetection.train
- Atribución de SFace: Yaoyao Zhong y colaboradores, *SFace: Sigmoid-Constrained Hypersphere Loss for Robust Face Recognition* (https://arxiv.org/abs/2205.12010), https://github.com/zhongyy/SFace. Conversión a ONNX: Chengrui Wang (OpenCV Zoo).
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

SFace: Apache License 2.0, texto completo en https://www.apache.org/licenses/LICENSE-2.0 y en `models/face_recognition_sface/LICENSE` de OpenCV Zoo.

## OCR
- **RapidOCR** (`rapidocr-onnxruntime` 1.4.4), Apache-2.0, https://github.com/RapidAI/RapidOCR. Incluye modelos **PP-OCR** de PaddleOCR (Apache-2.0).

## Bibliotecas
OpenCV (Apache-2.0), ONNX Runtime (MIT), FastAPI (MIT), Uvicorn (BSD-3), Pillow (MIT-CMU/HPND), NumPy (BSD-3), React (MIT), Vite (MIT), Tailwind CSS (MIT), Lucide (ISC), Playwright (Apache-2.0, solo para pruebas).

## Imágenes de prueba
Los tests E2E descargan `messi5.jpg` y `lena.jpg` de `opencv/opencv/samples/data` para generar fixtures **funcionales**. No se incluyen en el repositorio ni se usan para medir precisión.
