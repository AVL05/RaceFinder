"""Compara CPU y GPU en tus fotos: tiempo por foto del OCR de dorsales y si da los mismos resultados.

Uso (desde backend/, con el entorno virtual activo):
    python tools/gpu_bench.py CARPETA_O_FOTOS... [--n 30] [--device cuda|dml|auto]

Qué mide:
  - OCR de dorsales en CPU y en la GPU pedida (mismas fotos, tras un calentamiento que no cuenta).
  - Que la GPU da lo mismo: mismos dorsales leídos que en CPU.
(Las caras siguen en CPU: OpenCV 5 ignora la GPU con sus modelos.)
Si la GPU no se activa de verdad, lo dice (ONNX Runtime vuelve a CPU en silencio si faltan librerías).
"""
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bibs import BibReader
from app.device import onnx_providers, resolve_ocr_device

EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def collect(paths, n):
    files = []
    for p in map(Path, paths):
        files += sorted(f for f in p.rglob("*") if f.suffix.lower() in EXT) if p.is_dir() else [p]
    if not files:
        sys.exit("No se encontraron fotos.")
    step = max(1, len(files) // n)
    return files[::step][:n]


def timed(fn, files):
    out, t0 = [], time.perf_counter()
    for f in files:
        out.append(fn(f))
    return out, (time.perf_counter() - t0) / len(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--n", type=int, default=30, help="número máximo de fotos (repartidas por la carpeta)")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "dml"])
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    files = collect(a.paths, a.n)
    print(f"{len(files)} fotos · proveedores ONNX: {onnx_providers()}\n")

    # ---------------- OCR ----------------
    gpu_dev = resolve_ocr_device(a.device)
    cpu, gpu = BibReader(device="cpu"), BibReader(device=gpu_dev)
    gpu.ocr  # carga y comprueba el proveedor real
    gpu_dev = gpu.device
    for r in (cpu, gpu):
        r.read(files[0])  # calentamiento (en CUDA la primera pasada compila kernels)
    res_cpu, t_cpu = timed(cpu.read, files)
    print(f"OCR   CPU        {t_cpu:6.2f} s/foto")
    if gpu_dev == "cpu":
        print("OCR   GPU        NO ACTIVA: ONNX Runtime no ofrece GPU (instala backend/requirements-gpu.txt) o no pudo cargarla (ver avisos)")
    else:
        res_gpu, t_gpu = timed(gpu.read, files)
        same = sum({d.number for d in c} == {d.number for d in g} for c, g in zip(res_cpu, res_gpu))
        print(f"OCR   GPU ({gpu_dev:4s}) {t_gpu:6.2f} s/foto   x{t_cpu / t_gpu:.2f} más rápido")
        print(f"      mismos dorsales en CPU y GPU: {same}/{len(files)} fotos "
              f"({sum(len(c) for c in res_cpu)} lecturas CPU, {sum(len(g) for g in res_gpu)} GPU)")


if __name__ == "__main__":
    main()
