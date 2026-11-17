"""Localización y lectura de dorsales.

Estrategia (MVP, sin modelo de dorsales entrenado):
 1. Imagen completa reducida (lado largo <= 1920) -> detector de texto DBNet + reconocedor
    (RapidOCR con modelos PP-OCR en ONNX).
 2. Mosaico 2x2 con solapamiento sobre una versión de ~3200 px, para dorsales pequeños.
 3. Filtro geométrico/semántico: solo tokens numéricos de 1-5 dígitos, cajas plausibles.
 4. Fusión de duplicados entre pasadas (mismo número y cajas solapadas).
La 'confianza' es la puntuación del OCR, NO una probabilidad calibrada.
"""
import re
import cv2
from dataclasses import dataclass, asdict, fields, replace

import numpy as np
from PIL import Image, ImageOps

# Solo se corrige letra->dígito cuando la mayoría del token ya son dígitos.
LETTER_TO_DIGIT = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "|": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}
MAX_DIGITS = 5


@dataclass
class Detection:
    number: str
    raw_text: str
    confidence: float
    bbox: list  # [x0,y0,x1,y1] en px de la imagen original

    def dict(self):
        return asdict(self)


def normalize_token(text: str):
    """Devuelve el número si el texto parece un dorsal, si no None."""
    t = re.sub(r"[\s\-_.·]", "", text.strip().upper())
    if not t or len(t) > MAX_DIGITS + 1:
        return None
    digits = sum(c.isdigit() for c in t)
    if digits == 0 or digits < len(t) * 0.66:
        return None
    t = "".join(c if c.isdigit() else LETTER_TO_DIGIT.get(c, "?") for c in t)
    if "?" in t or not (1 <= len(t) <= MAX_DIGITS):
        return None
    return t


@dataclass(frozen=True)
class BibConfig:
    """Parámetros ajustables. Solo deben ajustarse con el conjunto 'tune' de la evaluación."""
    min_conf: float = 0.5        # puntuación mínima del reconocedor
    min_box_px: int = 14         # alto mínimo (px de la imagen original) de la caja de texto
    min_box_frac: float = 0.012  # ... y como fracción del alto de la imagen
    max_aspect: float = 8.0      # ancho/alto máximo de la caja
    full_max: int = 1920         # lado largo de la pasada global
    tile_max: int = 3200         # lado largo de la imagen sobre la que se hace el mosaico
    tile_trigger: int = 2400     # solo se hace mosaico si el lado largo original lo supera (0 = nunca)
    tile_frac: float = 0.55      # tamaño de cada baldosa respecto a la imagen reducida
    two_stage: bool = True       # 1) detectar cajas, 2) reconocer solo las plausibles (más rápido)
    use_cls: bool = False        # clasificador de ángulo 180º (caro; los dorsales casi nunca están boca abajo)
    tile_policy: str = "si_vacio"  # mosaico: siempre | si_vacio (solo si la pasada global no encontró dorsales) | nunca

    @classmethod
    def from_dict(cls, d):
        names = {f.name for f in fields(cls)}
        unknown = set(d) - names
        if unknown:
            raise ValueError(f"Parámetros desconocidos: {sorted(unknown)}")
        def cast(k, v):
            t = type(getattr(cls(), k))
            if t is bool:
                return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "si", "sí", "yes")
            return t(v)
        return replace(cls(), **{k: cast(k, v) for k, v in d.items()})

    def dict(self):
        return asdict(self)


def box_ok(w, h, img_h, cfg=None):
    cfg = cfg or BibConfig()
    if h < max(cfg.min_box_px, img_h * cfg.min_box_frac):  # demasiado pequeño para leerse con fiabilidad
        return False
    if w < h * 0.3 or w > h * cfg.max_aspect:               # proporciones imposibles
        return False
    return True


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0


def merge(dets):
    out = []
    for d in sorted(dets, key=lambda d: -d.confidence):
        if any(o.number == d.number and _iou(o.bbox, d.bbox) > 0.3 for o in out):
            continue
        out.append(d)
    return out


def similar_numbers(a: str, b: str) -> bool:
    """True si b está a distancia de edición 1 de a (sustitución, inserción o borrado)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    s, l = (a, b) if len(a) < len(b) else (b, a)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


class BibReader:
    engine_name = "rapidocr-onnx-ppocr"

    def __init__(self, cfg=None, ocr=None):
        self.cfg = cfg or BibConfig()
        self._ocr = ocr

    def with_config(self, cfg):
        """Misma sesión ONNX (carga costosa), otros parámetros."""
        return BibReader(cfg, ocr=self.ocr)

    @property
    def ocr(self):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        return self._ocr

    def _run(self, arr_rgb, scale, offset, orig_h):
        res, _ = self.ocr(np.ascontiguousarray(arr_rgb[:, :, ::-1]))
        found = []
        for box, text, score in (res or []):
            score = float(score)
            number = normalize_token(text)
            if number is None or score < self.cfg.min_conf:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            if not box_ok((x1 - x0) / scale, (y1 - y0) / scale, orig_h, self.cfg):
                continue
            bb = [int((x0 + offset[0]) / scale), int((y0 + offset[1]) / scale),
                  int((x1 + offset[0]) / scale), int((y1 + offset[1]) / scale)]
            found.append(Detection(number, text, round(score, 4), bb))
        return found

    def _crop(self, img, box):
        """Recorte rectificado del cuadrilátero (corrige inclinación), como hace RapidOCR internamente."""
        pts = np.array(box, dtype=np.float32)
        w = int(max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[2] - pts[3])))
        h = int(max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2])))
        if w < 2 or h < 2:
            return None
        dst = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        out = cv2.warpPerspective(img, cv2.getPerspectiveTransform(pts, dst), (w, h), borderMode=cv2.BORDER_REPLICATE)
        if h / w >= 1.5:
            out = np.rot90(out)
        return np.ascontiguousarray(out)

    def _run2(self, arr_rgb, scale, offset, orig_h):
        c = self.cfg
        bgr = np.ascontiguousarray(arr_rgb[:, :, ::-1])
        boxes, _ = self.ocr(bgr, use_det=True, use_cls=False, use_rec=False)
        crops, metas = [], []
        for box in (boxes or []):
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            bw = np.linalg.norm(np.subtract(box[0], box[1]))
            bh = np.linalg.norm(np.subtract(box[1], box[2]))
            if bh > bw * 1.5:  # texto vertical: intercambiar
                bw, bh = bh, bw
            if not box_ok(bw / scale, bh / scale, orig_h, c):
                continue  # evita reconocer cajas que nunca serían un dorsal
            crop = self._crop(bgr, box)
            if crop is not None:
                crops.append(crop)
                metas.append((min(xs), min(ys), max(xs), max(ys)))
        if not crops:
            return []
        # reconocimiento en lote (mucho más rápido que caja a caja)
        if c.use_cls:
            crops, _, _ = self.ocr.text_cls(crops)
        rec, _ = self.ocr.text_rec(crops)
        found = []
        for (x0, y0, x1, y1), (text, score) in zip(metas, rec):
            score = float(score)
            number = normalize_token(text)
            if number is None or score < c.min_conf:
                continue
            bb = [int((x0 + offset[0]) / scale), int((y0 + offset[1]) / scale),
                  int((x1 + offset[0]) / scale), int((y1 + offset[1]) / scale)]
            found.append(Detection(number, text, round(score, 4), bb))
        return found

    def read(self, path) -> list:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            W, H = im.size
            dets = []
            c = self.cfg
            run = self._run2 if c.two_stage else self._run
            s1 = min(1.0, c.full_max / max(W, H))
            a = np.asarray(im.resize((max(1, int(W * s1)), max(1, int(H * s1))), Image.LANCZOS) if s1 < 1 else im)
            dets += run(a, s1, (0, 0), H)
            tile = c.tile_trigger and max(W, H) > c.tile_trigger and (
                c.tile_policy == "siempre" or (c.tile_policy == "si_vacio" and not dets))
            if tile:
                s2 = min(1.0, c.tile_max / max(W, H))
                big = im.resize((int(W * s2), int(H * s2)), Image.LANCZOS) if s2 < 1 else im
                bw, bh = big.size
                tw, th = int(bw * c.tile_frac), int(bh * c.tile_frac)
                for ox in (0, bw - tw):
                    for oy in (0, bh - th):
                        chunk = np.asarray(big.crop((ox, oy, ox + tw, oy + th)))
                        dets += run(chunk, s2, (ox, oy), H)
        return merge(dets)
