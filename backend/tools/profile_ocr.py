"""Perfila el coste de cada fase de RapidOCR (deteccion / clasificador / reconocimiento) y de los hilos ONNX."""
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from rapidocr_onnxruntime import RapidOCR

img = Image.open(sys.argv[1]).convert("RGB")
for side in (1280, 1920, 3000):
    s = side / max(img.size)
    a = np.asarray(img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS))[:, :, ::-1].copy()
    for label, kw in (("det+cls+rec", {}), ("det+rec (sin cls)", {"use_cls": False}), ("solo det", {"use_cls": False, "use_rec": False})):
        ocr = RapidOCR()
        ocr(a, **kw)  # calentamiento
        t = time.perf_counter()
        n = 3
        for _ in range(n):
            res, el = ocr(a, **kw)
        print(f"{side}px {label:18s} {(time.perf_counter() - t) / n:.2f}s  cajas={len(res) if res else 0}")
