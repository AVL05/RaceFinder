"""Validación, almacenamiento byte-exacto de originales y miniaturas."""
import hashlib
import io
import os
import re
import shutil
import uuid
from pathlib import Path

from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = None  # lo controlamos nosotros con max_pixels


HEAD_BYTES = 64 * 1024


def head_hash(path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read(HEAD_BYTES)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class InvalidImage(Exception):
    pass


def safe_name(name: str) -> str:
    """Solo para mostrar. Nunca se usa para construir rutas."""
    name = os.path.basename((name or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f]", "", name).strip()
    return name[:200] or "foto"


def original_path(settings, sha: str, ext: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", sha) or ext not in settings.allowed_ext:
        raise ValueError("clave de archivo inválida")
    return settings.originals / sha[:2] / f"{sha}{ext}"


def thumb_path(settings, sha: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("clave inválida")
    return settings.thumbs / sha[:2] / f"{sha}.jpg"


def _validate(settings, path):
    """Comprueba con Pillow que es una imagen admitida. Devuelve (formato, ancho, alto) tal como se ve."""
    try:
        with Image.open(path) as im:
            fmt, (w, hgt) = im.format, im.size
            if fmt not in settings.allowed_formats:
                raise InvalidImage(f"Formato no admitido: {fmt}")
            if w * hgt > settings.max_pixels:
                raise InvalidImage("Imagen con demasiados píxeles")
            im.verify()  # debe llamarse justo tras open(); invalida el objeto
        with Image.open(path) as im2:  # reabrir para leer EXIF: dimensiones tal como se ven
            if im2.getexif().get(0x0112, 1) in (5, 6, 7, 8):
                w, hgt = hgt, w
    except InvalidImage:
        raise
    except Exception as e:
        raise InvalidImage(f"No es una imagen válida ({type(e).__name__})")
    return fmt, w, hgt


def ingest_path(settings, src):
    """Como ingest(), pero desde un archivo del disco: se lee una sola vez (para el hash) y no se copia a tmp.
    Es lo que hace rápida la importación de carpetas: no hay subida HTTP ni copia intermedia."""
    src = Path(src)
    ext = src.suffix.lower()
    if ext not in settings.allowed_ext:
        raise InvalidImage(f"Extensión no admitida: {ext or '(ninguna)'}")
    h, size = hashlib.sha256(), 0
    with open(src, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            size += len(chunk)
            if size > settings.max_file_bytes:
                raise InvalidImage("Archivo demasiado grande")
            h.update(chunk)
    if size == 0:
        raise InvalidImage("Archivo vacío")
    fmt, w, hgt = _validate(settings, src)
    ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[fmt]
    return {"sha256": h.hexdigest(), "head": head_hash(src), "ext": ext, "size": size, "width": w, "height": hgt, "src_path": src}


def commit_from_path(settings, meta):
    """Deja el original dentro de RaceFinder: enlace duro si el disco lo permite (instantáneo y sin ocupar
    más espacio), si no copia. Devuelve 'linked', 'copied' o None si ya existía."""
    dest = original_path(settings, meta["sha256"], meta["ext"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return None
    try:
        os.link(meta["src_path"], dest)
        return "linked"
    except FileExistsError:
        return None
    except OSError:
        pass  # otro disco, sistema sin enlaces duros...
    tmp = settings.tmp / f"{uuid.uuid4().hex}.part"
    try:
        shutil.copyfile(meta["src_path"], tmp)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return "copied"


def ingest(settings, stream, filename: str):
    """Guarda el flujo en tmp (con límite de tamaño), valida con Pillow, calcula sha256.
    No recodifica. Devuelve dict con metadatos y 'tmp_path'."""
    ext = Path(filename or "").suffix.lower()
    if ext not in settings.allowed_ext:
        raise InvalidImage(f"Extensión no admitida: {ext or '(ninguna)'}")
    tmp = settings.tmp / f"{uuid.uuid4().hex}.part"
    h = hashlib.sha256()
    head = hashlib.sha256()  # huella rápida (primeros 64 KB) para saber sin subir de nuevo si ya está importada
    size = 0
    try:
        with open(tmp, "wb") as f:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_file_bytes:
                    raise InvalidImage("Archivo demasiado grande")
                h.update(chunk)
                if size - len(chunk) < HEAD_BYTES:
                    head.update(chunk[:HEAD_BYTES - (size - len(chunk))])
                f.write(chunk)
        if size == 0:
            raise InvalidImage("Archivo vacío")
        fmt, w, hgt = _validate(settings, tmp)
        # la extensión canónica sale del formato real, no del nombre del cliente
        ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[fmt]
        return {"sha256": h.hexdigest(), "head": head.hexdigest(), "ext": ext, "size": size, "width": w, "height": hgt, "tmp_path": tmp}
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def commit_original(settings, meta) -> bool:
    """Mueve tmp -> originals. False si ya existía (duplicado)."""
    dest = original_path(settings, meta["sha256"], meta["ext"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        Path(meta["tmp_path"]).unlink(missing_ok=True)
        return False
    os.replace(meta["tmp_path"], dest)
    return True


def preview_path(settings, sha: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("clave inválida")
    return settings.previews / sha[:2] / f"{sha}.jpg"


def make_thumb(settings, sha: str, ext: str):
    return _derive(settings, sha, ext, thumb_path(settings, sha), settings.thumb_size, 82)


def make_preview(settings, sha: str, ext: str):
    """Versión de 1600 px para el visor: evita cargar originales de decenas de MB."""
    return _derive(settings, sha, ext, preview_path(settings, sha), settings.preview_size, 88)


def _derive(settings, sha, ext, dst, size, quality):
    src = original_path(settings, sha, ext)
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        if im.format == "JPEG":
            im.draft("RGB", (size, size))  # decodificación reducida: mucho más rápida en fotos de 20+ MP
        im = ImageOps.exif_transpose(im)
        im.thumbnail((size, size), Image.LANCZOS)
        im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
    _atomic_write(dst, buf.getvalue())
    return dst


def _atomic_write(dst: Path, data: bytes):
    tmp = dst.with_name(f"{dst.name}.{uuid.uuid4().hex}.tmp")  # único: peticiones concurrentes no se pisan
    tmp.write_bytes(data)
    try:
        os.replace(tmp, dst)
    except OSError:
        tmp.unlink(missing_ok=True)
        if not dst.exists():
            raise


def make_crop(settings, sha: str, ext: str, bbox, pad=(0.6, 0.9), size=(320, 200)):
    """Recorte del dorsal detectado (con margen) para verlo de un vistazo en los resultados."""
    x0, y0, x1, y1 = (int(v) for v in bbox)
    if x1 <= x0 or y1 <= y0:
        return None
    dst = settings.crops / sha[:2] / f"{sha}_{x0}_{y0}_{x1}_{y1}.jpg"
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(original_path(settings, sha, ext)) as im:
        im = ImageOps.exif_transpose(im)
        w, h = x1 - x0, y1 - y0
        pad_x, pad_y = int(w * pad[0]), int(h * pad[1])
        box = (max(0, x0 - pad_x), max(0, y0 - pad_y), min(im.width, x1 + pad_x), min(im.height, y1 + pad_y))
        c = im.crop(box).convert("RGB")
        c.thumbnail(size, Image.LANCZOS)
        buf = io.BytesIO()
        c.save(buf, "JPEG", quality=85)
    _atomic_write(dst, buf.getvalue())
    return dst
