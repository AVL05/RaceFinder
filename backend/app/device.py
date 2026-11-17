"""Selección del dispositivo de cálculo (CPU o GPU) para el OCR de dorsales y el reconocimiento facial.

Se controla con variables de entorno, sin tocar código:
  RACEFINDER_DEVICE  auto (por defecto) | cpu | cuda | dml   -> OCR de dorsales (ONNX Runtime)

Las caras (OpenCV 5 DNN) siguen en CPU: probado, su objetivo OpenCL se ignora y no da ninguna ganancia.

'auto' usa la GPU solo si el paquete de ONNX Runtime instalado la ofrece (onnxruntime-gpu u onnxruntime-directml);
con el onnxruntime normal (solo CPU) todo funciona exactamente igual que antes. Si se pide una GPU que no está
disponible, se avisa en el registro y se usa la CPU: nunca se interrumpe el procesado por esto.
"""
import logging
import os

log = logging.getLogger("racefinder.device")

OCR_DEVICES = ("auto", "cpu", "cuda", "dml")

_CUDA_EP = "CUDAExecutionProvider"
_DML_EP = "DmlExecutionProvider"


def _env(name, valid):
    v = (os.environ.get(name) or "auto").strip().lower()
    if v not in valid:
        log.warning("%s=%r no es válido (usa %s); se usa 'auto'", name, v, "|".join(valid))
        return "auto"
    return v


def onnx_providers():
    try:
        import onnxruntime
        return list(onnxruntime.get_available_providers())
    except Exception:  # pragma: no cover - onnxruntime siempre está instalado con rapidocr
        return []


def preload_cuda_libs():
    """Con las librerías CUDA/cuDNN instaladas como paquetes pip (nvidia-*), ONNX Runtime necesita cargarlas
    explícitamente. Si no existe la función o no hay librerías, no pasa nada."""
    try:
        import onnxruntime
        onnxruntime.preload_dlls()
    except Exception:
        pass


def resolve_ocr_device(requested=None):
    """Devuelve 'cuda', 'dml' o 'cpu' según lo pedido y lo que ofrece el onnxruntime instalado."""
    req = (requested or _env("RACEFINDER_DEVICE", OCR_DEVICES)).lower()
    prov = onnx_providers()
    if req == "cpu":
        return "cpu"
    if req in ("auto", "cuda") and _CUDA_EP in prov:
        preload_cuda_libs()
        return "cuda"
    if req in ("auto", "dml") and _DML_EP in prov:
        return "dml"
    if req != "auto":
        log.warning("RACEFINDER_DEVICE=%s pedido pero ONNX Runtime solo ofrece %s: se usa la CPU. "
                    "Instala onnxruntime-gpu (CUDA) u onnxruntime-directml (ver backend/requirements-gpu.txt).",
                    req, prov)
    return "cpu"


def ocr_kwargs(device):
    """Parámetros de RapidOCR para activar el proveedor de GPU en detección, clasificador y reconocedor."""
    if device == "cuda":
        return {"det_use_cuda": True, "cls_use_cuda": True, "rec_use_cuda": True}
    if device == "dml":
        return {"det_use_dml": True, "cls_use_dml": True, "rec_use_dml": True}
    return {}


def session_providers(ocr):
    """Proveedores que ONNX Runtime ha activado de verdad en el detector (RapidOCR vuelve a CPU sin avisar
    si no puede cargar la GPU, así que esto es lo que hay que comprobar)."""
    try:
        return list(ocr.text_det.infer.session.get_providers())
    except Exception:
        return []
