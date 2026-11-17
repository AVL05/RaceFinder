"""Reducción de fotos para el análisis (dorsales y caras), con un modo rápido opcional.

Reducir con PIL Lanczos es de lo más caro del procesado de una foto de cámara (~75-215 ms), más que la propia
inferencia en GPU. `cv2.resize(INTER_AREA)` es ~3-9x más rápido con calidad equivalente al reducir, pero cambia
ligeramente los píxeles (diferencia media ~0,15/255), así que puede cambiar alguna lectura o detección límite.
Por eso está APAGADO por defecto: actívalo con RACEFINDER_FAST_RESIZE=1 tras comprobarlo con tools/gpu_bench.py
(compara dorsales y caras con y sin él sobre tus fotos).
"""
import os

import cv2
import numpy as np
from PIL import Image

_override = None  # solo para pruebas y para tools/gpu_bench.py


def set_fast(value):
    """Fuerza el modo (True/False) o vuelve a leer la variable de entorno (None)."""
    global _override
    _override = value


def fast_enabled():
    if _override is not None:
        return _override
    return os.environ.get("RACEFINDER_FAST_RESIZE", "0").strip().lower() in ("1", "true", "si", "sí", "yes", "on")


def resize_rgb(im, size):
    """Reduce una imagen PIL RGB a size=(ancho, alto) y devuelve un array RGB uint8."""
    w, h = size
    if fast_enabled():
        return cv2.resize(np.asarray(im), (w, h), interpolation=cv2.INTER_AREA)
    return np.asarray(im.resize((w, h), Image.LANCZOS))
