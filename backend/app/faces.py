"""Reconocimiento facial local y opcional (OpenCV YuNet + SFace, licencias Apache-2.0 / MIT).

Principios:
 - Solo se activa si el usuario lo pide expresamente; se puede borrar todo con un botón.
 - No se guardan identidades ni nombres: solo vectores anónimos por cara detectada.
 - Solo se busca a partir de caras de referencia que el usuario elige y confirma.
 - La similitud es un coseno entre vectores, NO una probabilidad.
"""
import hashlib
import os
import threading
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

MODELS = {
    # 2026may: re-exportación oficial de 2023mar con entrada dinámica, la recomendada para OpenCV 5.x.
    # Verificado en OpenCV 5.0.0: mismas detecciones que 2023mar (mismas cajas, IoU 1,0) a 3 resoluciones.
    "det": ("face_detection_yunet_2026may.onnx",
            "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2026may.onnx",
            "ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0"),
    "rec": ("face_recognition_sface_2021dec.onnx",
            "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
            "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}
MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
EMB_DIM = 128
# Umbral de coseno publicado por OpenCV para SFace (samples/dnn/face_detect.py: cosine_similarity_threshold = 0.363).
# No se ha recalibrado: falta un conjunto real etiquetado. Ajustarlo solo con la partición 'tune'.
MATCH_THRESHOLD = 0.363
STRONG_THRESHOLD = 0.5
DETECT_MAX_SIDE = 2560
MIN_FACE_PX = 22          # caras más pequeñas no dan vectores fiables

_lock = threading.Lock()


def models_ready(models_dir=MODELS_DIR) -> bool:
    return all((models_dir / f).exists() for f, _, _ in MODELS.values())


def ensure_models(models_dir=MODELS_DIR):
    """Descarga los modelos oficiales de OpenCV Zoo una sola vez y verifica su SHA-256."""
    with _lock:
        models_dir.mkdir(parents=True, exist_ok=True)
        for fname, url, sha in MODELS.values():
            dst = models_dir / fname
            if dst.exists():
                continue
            tmp = dst.with_suffix(".part")
            h = hashlib.sha256()
            with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    h.update(chunk)
                    f.write(chunk)
            if h.hexdigest() != sha:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"El modelo {fname} descargado no coincide con el original")
            os.replace(tmp, dst)


class FaceEngine:
    def __init__(self, models_dir=MODELS_DIR):
        self.models_dir = models_dir
        self._det = self._rec = None

    def _load(self):
        if self._det is None:
            ensure_models(self.models_dir)
            self._det = cv2.FaceDetectorYN.create(str(self.models_dir / MODELS["det"][0]), "", (320, 320), 0.8, 0.3, 5000)
            self._rec = cv2.FaceRecognizerSF.create(str(self.models_dir / MODELS["rec"][0]), "")

    def index(self, path):
        """Devuelve [(bbox [x0,y0,x1,y1] en px de la imagen tal como se ve, puntuación, vector float32 normalizado)]."""
        self._load()
        with Image.open(path) as raw:
            W, H = raw.size  # tamaño tal como se ve (antes de la decodificación reducida)
            if raw.getexif().get(0x0112, 1) in (5, 6, 7, 8):
                W, H = H, W
            if raw.format == "JPEG":
                raw.draft("RGB", (DETECT_MAX_SIDE, DETECT_MAX_SIDE))
            im = ImageOps.exif_transpose(raw).convert("RGB")
        s = min(1.0, DETECT_MAX_SIDE / max(im.size))
        if s < 1:
            im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        bgr = np.ascontiguousarray(np.asarray(im)[:, :, ::-1])
        h, w = bgr.shape[:2]
        self._det.setInputSize((w, h))
        _, faces = self._det.detect(bgr)
        out = []
        k = W / w  # factor a coordenadas de la imagen original
        for f in (faces if faces is not None else []):
            x, y, fw, fh = f[:4]
            if min(fw, fh) < MIN_FACE_PX:
                continue
            emb = self._rec.feature(self._rec.alignCrop(bgr, f)).astype(np.float32).ravel()
            emb /= (np.linalg.norm(emb) or 1.0)
            bbox = [int(max(0, x) * k), int(max(0, y) * k), int(min(w, x + fw) * k), int(min(h, y + fh) * k)]
            out.append((bbox, float(f[-1]), emb))
        return out


def to_blob(emb):
    return np.asarray(emb, dtype=np.float32).tobytes()


def from_blob(b):
    return np.frombuffer(b, dtype=np.float32)


def associate(bib_bbox, faces):
    """Elige la cara que con más probabilidad pertenece al corredor del dorsal: encima del dorsal,
    centrada horizontalmente y a una distancia compatible con un torso. No es una certeza: el usuario confirma."""
    x0, y0, x1, y1 = bib_bbox
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    cx = (x0 + x1) / 2
    best, best_d = None, None
    for f in faces:
        fx0, fy0, fx1, fy1 = f["bbox"]
        fh = max(1, fy1 - fy0)
        fcx = (fx0 + fx1) / 2
        if fy1 > y0 + 0.25 * bh:                # la cara debe estar por encima del dorsal
            continue
        if abs(fcx - cx) > 0.9 * bw + fh:       # alineada con el torso
            continue
        gap = y0 - fy1
        if gap > 6 * fh or not (0.15 < fh / bh < 4):  # distancia y escala plausibles
            continue
        d = abs(fcx - cx) / bw + gap / (3 * fh)
        if best_d is None or d < best_d:
            best, best_d = f, d
    return best


# ---------------------------------------------------------------------------
# Núcleo de búsqueda compartido por la API y por la evaluación (mismo comportamiento en ambos).

def _rows(conn, where="", args=()):
    return conn.execute(f"SELECT id, photo_id, bbox, score, emb FROM faces {where}", args).fetchall()


def candidates_for_bib(conn, bib, doubtful_below):
    """Caras de las fotos en las que se leyó `bib`. Marca la asociada al dorsal y decide cuáles preseleccionar:
    solo las asociadas a lecturas fiables (o confirmadas) y que no desentonan con las demás."""
    import json
    dets = conn.execute("SELECT photo_id, bbox, confidence, review FROM bib_detections "
                        "WHERE number=? AND review!='rejected'", (bib,)).fetchall()
    by_photo = {}
    for d in dets:
        trusted = d["review"] in ("confirmed", "manual") or d["confidence"] >= doubtful_below
        by_photo.setdefault(d["photo_id"], []).append((json.loads(d["bbox"]), trusted))
    out = []
    for pid, bibs in by_photo.items():
        fs = [{"id": f["id"], "photo_id": pid, "bbox": json.loads(f["bbox"]), "score": f["score"],
               "emb": from_blob(f["emb"]), "associated": False, "trusted_bib": False, "consistent": None}
              for f in _rows(conn, "WHERE photo_id=?", (pid,))]
        for bbox, trusted in bibs:
            if bbox[2] > 0:
                a = associate(bbox, fs)
                if a is not None:
                    a["associated"] = True
                    a["trusted_bib"] = a["trusted_bib"] or trusted
        out.extend(fs)
    assoc = [f for f in out if f["associated"]]
    # coherencia "dejando una fuera": cada cara se compara con la media de las DEMÁS asociadas
    if len(assoc) >= 3:
        E = np.stack([f["emb"] for f in assoc])
        total = E.sum(axis=0)
        for f, e in zip(assoc, E):
            m = total - e
            m = m / (np.linalg.norm(m) or 1)
            f["consistent"] = bool(float(e @ m) >= MATCH_THRESHOLD)
    for f in out:
        f["preselect"] = f["associated"] and f["trusted_bib"] and f["consistent"] is not False
    out.sort(key=lambda f: (not f["preselect"], not f["associated"], -f["score"]))
    return list(by_photo), out


def _matrix(rows):
    """Vectores de muchas filas en una sola matriz (una copia en bloque, no una por cara)."""
    return np.frombuffer(b"".join(r["emb"] for r in rows), dtype=np.float32).reshape(len(rows), EMB_DIM)


def search(conn, face_ids, threshold=MATCH_THRESHOLD):
    """{photo_id: (similitud, fila de la cara)} con el coseno máximo contra cualquiera de las caras de referencia."""
    if not face_ids:
        return {}
    refs = _rows(conn, f"WHERE id IN ({','.join('?' * len(face_ids))})", list(face_ids))
    rows = _rows(conn)
    if not refs or not rows:
        return {}
    sims = _matrix(rows) @ _matrix(refs).T
    best = {}
    for r, sim in zip(rows, sims.max(axis=1)):
        sim = float(sim)
        if sim >= threshold and (r["photo_id"] not in best or sim > best[r["photo_id"]][0]):
            best[r["photo_id"]] = (sim, r)
    return best
