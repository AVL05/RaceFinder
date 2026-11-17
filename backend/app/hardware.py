"""Ajuste automático a la máquina: cuántas fotos procesar a la vez y prioridad del proceso.

La web se publica para que cualquiera la use en local, en equipos muy distintos (un portátil de 8 GB o una torre
con 32 GB y GPU). Un número fijo de hilos no sirve para todos: demasiados hilos saturan la CPU y la RAM (cada foto
de cámara descomprimida ocupa decenas de MB y cada hilo mantiene varias copias); demasiado pocos dejan la GPU parada.
Todo se puede forzar con variables de entorno (RACEFINDER_WORKERS, RACEFINDER_PRIORITY).
"""
import ctypes
import logging
import os

log = logging.getLogger("racefinder.hardware")

MAX_WORKERS = 16
GB_PER_WORKER = 1.5   # medido: ~0,5-1 GB por hilo con fotos de 20 MP (imagen, copias reducidas y búferes de ONNX)
RESERVED_GB = 4.0     # memoria que se deja libre para el sistema, el navegador y la propia web


def total_ram_gb():
    """RAM física total en GB, o None si no se puede saber."""
    try:
        if os.name == "nt":
            class MEM(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("tpf", ctypes.c_ulonglong), ("apf", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ave", ctypes.c_ulonglong)]
            m = MEM()
            m.length = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.total / 2**30
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except Exception:
        return None


def auto_workers(device="cpu", cores=None, ram_gb=None):
    """Fotos a la vez recomendadas.

    Con GPU la inferencia ya no pesa: lo que limita es decodificar y reducir fotos en CPU, así que se reparten los
    hilos lógicos a razón de ~1 trabajador por cada 3. Solo con CPU, ONNX Runtime ya usa todos los núcleos en cada
    foto y más de 3 hilos no ayuda (solo gasta RAM). En ambos casos la RAM pone un tope.
    """
    cores = cores or os.cpu_count() or 2
    ram_gb = ram_gb if ram_gb is not None else total_ram_gb()
    if device == "cpu":
        n = 3 if cores >= 8 else 2 if cores >= 4 else 1
    else:
        n = max(2, cores // 3)
    if ram_gb:
        n = min(n, max(1, int((ram_gb - RESERVED_GB) // GB_PER_WORKER)))
    return max(1, min(MAX_WORKERS, n))


def lower_priority():
    """Prioridad algo menor que la normal: el análisis tarda horas y así el resto del equipo (navegador, la propia
    interfaz) sigue ágil aunque la CPU esté al máximo. Apagar con RACEFINDER_PRIORITY=normal."""
    if (os.environ.get("RACEFINDER_PRIORITY") or "low").strip().lower() in ("normal", "0", "no", "off"):
        return
    try:
        if os.name == "nt":
            BELOW_NORMAL = 0x00004000
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL)
        else:
            os.nice(5)
    except Exception as e:  # nunca debe impedir el arranque
        log.warning("No se pudo bajar la prioridad del proceso: %s", e)
