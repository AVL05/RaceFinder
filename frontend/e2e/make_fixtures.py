"""Fixtures FUNCIONALES para el E2E (no sirven para medir precisión).

- Corredores sintéticos con dorsal (tools/synth.py) para el flujo de dorsales.
- Dos caras reales de las imágenes de ejemplo de OpenCV (messi5.jpg, lena.jpg; BSD/Apache, repositorio opencv/opencv)
  pegadas sobre corredores sintéticos para ejercitar la interfaz de búsqueda por cara.
  Por diseño son la misma cara pegada varias veces: las similitudes salen artificialmente altas.
Uso: python make_fixtures.py <carpeta_cache> <carpeta_salida>
"""
import hashlib
import random
import sys
import urllib.request
from pathlib import Path

import cv2
from PIL import Image

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND / "tools"))
sys.path.insert(0, str(BACKEND))
import synth  # noqa: E402
from app.faces import MODELS, MODELS_DIR, ensure_models  # noqa: E402

SAMPLES = {
    "messi.jpg": "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/messi5.jpg",
    "lena.jpg": "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/lena.jpg",
}

cache, out = Path(sys.argv[1]), Path(sys.argv[2])
cache.mkdir(parents=True, exist_ok=True)
out.mkdir(parents=True, exist_ok=True)
for name, url in SAMPLES.items():
    if not (cache / name).exists():
        urllib.request.urlretrieve(url, cache / name)
ensure_models()
det = cv2.FaceDetectorYN.create(str(MODELS_DIR / MODELS["det"][0]), "", (320, 320), 0.8, 0.3, 5000)


def face_crop(path):
    img = cv2.imread(str(path)); h, w = img.shape[:2]
    det.setInputSize((w, h)); _, f = det.detect(img)
    x, y, fw, fh = [int(v) for v in f[0][:4]]
    pad = int(fw * 0.35)
    return Image.fromarray(img[max(0, y - pad):y + fh + pad, max(0, x - pad):x + fw + pad][:, :, ::-1])


FACES = {"A": face_crop(cache / "messi.jpg"), "B": face_crop(cache / "lena.jpg")}


def scene(people, seed, name):
    rng = random.Random(seed)
    bg = synth.background(rng, False)
    for k, (who, bib, scale) in enumerate(people):
        cx = int(synth.W * (k + 0.5) / len(people))
        cx, top, tw, th, _ = synth.runner(bg, cx, int(synth.H * 0.75), scale, rng)
        f = FACES[who]; fw = int(170 * scale)
        fimg = f.resize((fw, int(fw * f.height / f.width)), Image.LANCZOS)
        bg.paste(fimg, (int(cx - fw / 2), int(top - fimg.height + 15 * scale)))
        if bib:
            b = synth.bib_image(bib, int(th * 0.42), rng)
            bg.paste(b, (int(cx - b.width / 2), int(top + th * 0.2)), b)
    bg.save(out / name, quality=92)


scene([("A", "184", 1.1)], 1, "a_dorsal.jpg")
scene([("A", "184", 0.9), ("B", "301", 0.9)], 2, "a_y_b_dorsales.jpg")
scene([("A", None, 1.0)], 3, "a_sin_dorsal.jpg")
scene([("B", None, 1.0), ("A", None, 0.8)], 4, "b_y_a_sin_dorsal.jpg")
scene([("B", "301", 1.1)], 5, "b_dorsal.jpg")
scene([("B", None, 1.0)], 6, "b_sin_dorsal.jpg")
# sin corredores con cara ni dorsal: debe seguir en el catálogo
rng = random.Random(7); synth.background(rng, True).save(out / "solo_fondo.jpg", quality=92)
print("fixtures:", sorted(p.name for p in out.glob("*.jpg")))
