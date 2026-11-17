"""YuNet + SFace sobre ONNX Runtime (ruta de GPU) deben dar lo mismo que OpenCV DNN (ruta de CPU de siempre).
Se prueba el motor de ONNX Runtime con su proveedor de CPU: es el mismo código y los mismos modelos que en GPU.
Usa las caras reales de ejemplo de OpenCV que descarga frontend/e2e/make_fixtures.py (se omite si no están)."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.faces import MODELS, MODELS_DIR, FaceEngine, OrtFaceModels, models_ready

CACHE = Path(__file__).resolve().parents[2] / "frontend" / "e2e" / ".fixtures" / "cache"
pytestmark = pytest.mark.skipif(not (models_ready() and (CACHE / "lena.jpg").exists() and (CACHE / "messi.jpg").exists()),
                                reason="faltan los modelos o las imágenes de ejemplo")


@pytest.fixture(scope="module")
def models():
    return OrtFaceModels(MODELS_DIR, "cpu")


@pytest.fixture(scope="module")
def cv_models():
    det = cv2.FaceDetectorYN.create(str(MODELS_DIR / MODELS["det"][0]), "", (320, 320), 0.8, 0.3, 5000)
    rec = cv2.FaceRecognizerSF.create(str(MODELS_DIR / MODELS["rec"][0]), "")
    return det, rec


def images():
    lena, messi = cv2.imread(str(CACHE / "lena.jpg")), cv2.imread(str(CACHE / "messi.jpg"))
    h = max(lena.shape[0], messi.shape[0])
    pad = lambda im: cv2.copyMakeBorder(im, 0, h - im.shape[0], 0, 0, cv2.BORDER_CONSTANT)
    return {
        "lena": lena,
        "messi": messi,
        "dos caras": np.hstack([pad(lena), pad(messi)]),
        "tamaño impar": lena[:487, :503].copy(),      # no múltiplo de 32: ejercita el relleno
        "reducida": cv2.resize(messi, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),
    }


@pytest.mark.parametrize("name", list(images()))
def test_ort_matches_opencv(models, cv_models, name):
    det, rec = cv_models
    img = images()[name]
    h, w = img.shape[:2]
    det.setInputSize((w, h))
    _, ref = det.detect(img)
    ref = ref if ref is not None else np.zeros((0, 15))
    got = models.detect(img)
    assert len(got) == len(ref) >= 1, "mismo número de caras"
    order_r, order_g = np.argsort(ref[:, 0]), np.argsort(got[:, 0])
    ref, got = ref[order_r], got[order_g]
    assert np.abs(ref[:, :14] - got[:, :14]).max() < 0.5, "cajas y puntos faciales a menos de medio píxel"
    assert np.abs(ref[:, 14] - got[:, 14]).max() < 1e-3, "puntuaciones"
    for fr, fg in zip(ref, got):
        crop_r, crop_g = rec.alignCrop(img, fr), models.align(img, fr)
        assert np.abs(crop_r.astype(int) - crop_g.astype(int)).mean() < 1.0, "recorte alineado 112x112"
        e_r = rec.feature(crop_r).ravel()
        e_g = models.embed(img, fr)
        cos = float(e_r @ e_g / (np.linalg.norm(e_r) * np.linalg.norm(e_g)))
        assert cos > 0.999, f"vector facial idéntico (coseno {cos:.5f})"


def test_ort_does_not_confuse_identities(models):
    """Control: lena y messi deben seguir siendo personas distintas con el motor de ONNX Runtime."""
    ims = images()
    e = [models.embed(ims[k], models.detect(ims[k])[0]) for k in ("lena", "messi")]
    cos = float(e[0] @ e[1] / (np.linalg.norm(e[0]) * np.linalg.norm(e[1])))
    assert cos < 0.363


def test_face_engine_gpu_request_falls_back_to_opencv(monkeypatch):
    """Si ONNX Runtime no puede activar la GPU, el motor sigue con OpenCV (CPU) sin fallar."""
    import app.faces as faces
    monkeypatch.setattr(faces, "_ort_cache", {})
    e = FaceEngine(device="cuda")   # este entorno no tiene CUDA
    e._load()
    assert e.device == "cpu" and e._det is not None and e._ort is None


def test_face_engine_index_same_on_both_backends(models, monkeypatch):
    """FaceEngine.index (lo que usa la aplicación) da las mismas caras con OpenCV y con ONNX Runtime."""
    a = FaceEngine(device="cpu")
    b = FaceEngine(device="cpu")
    b._ort = models
    b._det = b._rec = None
    img = str(CACHE / "messi.jpg")
    ra, rb = a.index(img), b.index(img)
    assert len(ra) == len(rb) >= 1
    for (bb_a, s_a, e_a), (bb_b, s_b, e_b) in zip(ra, rb):
        assert max(abs(x - y) for x, y in zip(bb_a, bb_b)) <= 1
        assert float(e_a @ e_b) > 0.999
