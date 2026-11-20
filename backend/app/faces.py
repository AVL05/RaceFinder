"""Reconocimiento facial local y opcional (OpenCV YuNet + SFace, licencias Apache-2.0 / MIT).

Principios:
 - Solo se activa si el usuario lo pide expresamente; se puede borrar todo con un botón.
 - No se guardan identidades ni nombres: solo vectores anónimos por cara detectada.
 - Solo se busca a partir de caras de referencia que el usuario elige y confirma.
 - La similitud es un coseno entre vectores, NO una probabilidad.
"""
import hashlib
import logging
import os
import threading
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from .device import resolve_face_device
from .resize import resize_rgb

log = logging.getLogger("racefinder.faces")

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


class OrtFaceModels:
    """YuNet + SFace sobre ONNX Runtime (permite GPU). Replica cv2.FaceDetectorYN y cv2.FaceRecognizerSF:
    mismas cajas, puntos faciales y vectores (se comprueba contra OpenCV en tests/test_faces_ort.py)."""
    STRIDES = (8, 16, 32)
    # Plantilla de 5 puntos en 112x112 (la misma que usa cv2.FaceRecognizerSF.alignCrop)
    DST = np.float32([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]])

    def __init__(self, models_dir=MODELS_DIR, device="cpu", providers=None, score_thr=0.8, nms_thr=0.3, top_k=5000):
        import onnxruntime as ort
        self.score_thr, self.nms_thr, self.top_k = score_thr, nms_thr, top_k
        so = ort.SessionOptions()
        so.log_severity_level = 3
        if device == "cuda":
            # HEURISTIC: el detector recibe tamaños distintos y EXHAUSTIVE reprobaría los algoritmos con cada tamaño nuevo
            providers = providers or [("CUDAExecutionProvider", {"cudnn_conv_algo_search": "HEURISTIC"}), "CPUExecutionProvider"]
        elif device == "dml":
            so.enable_mem_pattern = False  # requisitos de DirectML
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            providers = providers or ["DmlExecutionProvider", "CPUExecutionProvider"]
        else:
            providers = providers or ["CPUExecutionProvider"]
        self.det = ort.InferenceSession(str(models_dir / MODELS["det"][0]), so, providers=providers)
        self.rec = ort.InferenceSession(str(models_dir / MODELS["rec"][0]), so, providers=providers)
        wanted = providers[0][0] if isinstance(providers[0], tuple) else providers[0]
        if self.det.get_providers()[0] != wanted or self.rec.get_providers()[0] != wanted:
            raise RuntimeError(f"ONNX Runtime no activó {wanted} para las caras (usa {self.det.get_providers()})")
        self.providers = self.det.get_providers()
        self._det_in = self.det.get_inputs()[0].name
        self._rec_in = self.rec.get_inputs()[0].name
        self._det_out = [o.name for o in self.det.get_outputs()]

    def detect(self, bgr):
        """Array (N, 15): x, y, w, h, 5 puntos (x, y) y puntuación, como cv2.FaceDetectorYN.detect."""
        h, w = bgr.shape[:2]
        ph, pw = ((h - 1) // 32 + 1) * 32, ((w - 1) // 32 + 1) * 32  # el modelo exige múltiplos de 32 (relleno abajo/derecha)
        blob = np.zeros((1, 3, ph, pw), np.float32)
        blob[0, :, :h, :w] = bgr.transpose(2, 0, 1)
        out = dict(zip(self._det_out, self.det.run(None, {self._det_in: blob})))
        rows = []
        for s in self.STRIDES:
            cols = pw // s
            cls, obj = out[f"cls_{s}"].reshape(-1), out[f"obj_{s}"].reshape(-1)
            sc = np.sqrt(np.clip(cls, 0, 1) * np.clip(obj, 0, 1))
            keep = np.nonzero(sc >= self.score_thr)[0]
            if not len(keep):
                continue
            bb, kp = out[f"bbox_{s}"].reshape(-1, 4)[keep], out[f"kps_{s}"].reshape(-1, 5, 2)[keep]
            c, r = (keep % cols).astype(np.float32), (keep // cols).astype(np.float32)
            bw, bh = np.exp(bb[:, 2]) * s, np.exp(bb[:, 3]) * s
            x, y = (c + bb[:, 0]) * s - bw / 2, (r + bb[:, 1]) * s - bh / 2
            lm = (kp + np.stack([c, r], axis=1)[:, None, :]) * s
            rows.append(np.column_stack([x, y, bw, bh, lm.reshape(-1, 10), sc[keep]]))
        if not rows:
            return np.zeros((0, 15), np.float32)
        faces = np.concatenate(rows).astype(np.float32)
        idx = cv2.dnn.NMSBoxes([[int(f[0]), int(f[1]), int(f[2]), int(f[3])] for f in faces], faces[:, -1].tolist(),
                               self.score_thr, self.nms_thr, 1.0, self.top_k)
        return faces[np.array(idx, dtype=int).reshape(-1)]

    @staticmethod
    def _similarity(src, dst):
        """Transformación de semejanza por mínimos cuadrados (Umeyama), la que usa OpenCV para alinear."""
        src, dst = np.asarray(src, np.float64), np.asarray(dst, np.float64)
        sm, dm = src.mean(0), dst.mean(0)
        s0, d0 = src - sm, dst - dm
        U, S, Vt = np.linalg.svd(d0.T @ s0 / len(src))
        d = np.array([1.0, -1.0 if np.linalg.det(U) * np.linalg.det(Vt) < 0 else 1.0])
        R = U @ np.diag(d) @ Vt
        scale = (S * d).sum() / ((s0 ** 2).sum() / len(src))
        return np.hstack([scale * R, (dm - scale * R @ sm)[:, None]])

    def align(self, bgr, face):
        M = self._similarity(np.asarray(face[4:14]).reshape(5, 2), self.DST)
        return cv2.warpAffine(bgr, M, (112, 112), flags=cv2.INTER_LINEAR)

    def embed(self, bgr, face):
        blob = cv2.dnn.blobFromImage(self.align(bgr, face), 1.0, (112, 112), (0, 0, 0), True, False)
        return self.rec.run(None, {self._rec_in: blob})[0].ravel()


_ort_cache = {}


def get_ort_models(models_dir, device):
    """Una sola carga de modelos para todos los hilos (las sesiones de ONNX Runtime son seguras entre hilos)."""
    with _lock:
        key = (str(models_dir), device)
        if key not in _ort_cache:
            _ort_cache[key] = OrtFaceModels(models_dir, device)
        return _ort_cache[key]


class FaceEngine:
    def __init__(self, models_dir=MODELS_DIR, device=None):
        self.models_dir = models_dir
        self.device = device or resolve_face_device()  # 'cpu' (OpenCV DNN, como siempre) | 'cuda' | 'dml' (ONNX Runtime)
        self._det = self._rec = self._ort = None

    def _load(self):
        if self._det is None and self._ort is None:
            ensure_models(self.models_dir)
            if self.device != "cpu":
                try:
                    self._ort = get_ort_models(self.models_dir, self.device)
                    log.info("Reconocimiento facial en GPU (%s)", self._ort.providers[0])
                    return
                except Exception as e:
                    log.warning("No se pudo usar la GPU (%s) para las caras (%s): se usa la CPU", self.device, e)
                    self.device = "cpu"
            self._det = cv2.FaceDetectorYN.create(str(self.models_dir / MODELS["det"][0]), "", (320, 320), 0.8, 0.3, 5000)
            self._rec = cv2.FaceRecognizerSF.create(str(self.models_dir / MODELS["rec"][0]), "")

    def _detect(self, bgr):
        if self._ort is not None:
            return self._ort.detect(bgr)
        h, w = bgr.shape[:2]
        self._det.setInputSize((w, h))
        _, faces = self._det.detect(bgr)
        return faces if faces is not None else []

    def _embed(self, bgr, f):
        if self._ort is not None:
            return self._ort.embed(bgr, f)
        return self._rec.feature(self._rec.alignCrop(bgr, f))

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
        rgb = resize_rgb(im, (int(im.width * s), int(im.height * s))) if s < 1 else np.asarray(im)
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        h, w = bgr.shape[:2]
        faces = self._detect(bgr)
        out = []
        k = W / w  # factor a coordenadas de la imagen original
        for f in faces:
            x, y, fw, fh = f[:4]
            if min(fw, fh) < MIN_FACE_PX:
                continue
            emb = np.asarray(self._embed(bgr, f), dtype=np.float32).ravel()
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


def candidates_for_bib(conn, bib, doubtful_below, album=None, number_range=None):
    """Caras de las fotos en las que se leyó `bib`. Marca la asociada al dorsal y decide cuáles preseleccionar:
    solo las asociadas a lecturas fiables (o confirmadas) y que no desentonan con las demás."""
    import json
    from .catalog import album_clause
    scope, args = album_clause(album, "photo_id")
    if number_range is not None:
        scope += " AND (review='manual' OR CAST(number AS INTEGER) BETWEEN ? AND ?)"
        args = (*args, *number_range)
    dets = conn.execute("SELECT photo_id, bbox, confidence, review FROM bib_detections "
                        f"WHERE number=? AND review!='rejected' AND {scope}", (bib, *args)).fetchall()
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


def search(conn, face_ids, threshold=MATCH_THRESHOLD, album=None):
    """{photo_id: (similitud, fila de la cara)} con el coseno máximo contra cualquiera de las caras de referencia."""
    if not face_ids:
        return {}
    from .catalog import album_clause
    scope, args = album_clause(album, "photo_id")
    refs = _rows(conn, f"WHERE id IN ({','.join('?' * len(face_ids))}) AND {scope}", (*face_ids, *args))
    rows = _rows(conn, f"WHERE {scope}", args)
    if not refs or not rows:
        return {}
    sims = _matrix(rows) @ _matrix(refs).T
    best = {}
    for r, sim in zip(rows, sims.max(axis=1)):
        sim = float(sim)
        if sim >= threshold and (r["photo_id"] not in best or sim > best[r["photo_id"]][0]):
            best[r["photo_id"]] = (sim, r)
    return best
