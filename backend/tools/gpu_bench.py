"""Compara CPU y GPU en tus fotos: tiempo por foto del OCR de dorsales y si da los mismos resultados.

Uso (desde backend/, con el entorno virtual activo):
    python tools/gpu_bench.py CARPETA_O_FOTOS... [--n 30] [--device cuda|dml|auto] [--no-faces]

Qué mide:
  - OCR de dorsales en CPU y en la GPU pedida (mismas fotos, tras un calentamiento que no cuenta).
  - Que la GPU da lo mismo: mismos dorsales leídos que en CPU.
  - Caras (YuNet + SFace): OpenCV en CPU frente a ONNX Runtime en GPU, y que den las mismas caras y vectores.
Si la GPU no se activa de verdad, lo dice (ONNX Runtime vuelve a CPU en silencio si faltan librerías).
"""
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bibs import BibReader
import numpy as np

from app.device import onnx_providers, resolve_ocr_device
from app.faces import FaceEngine

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
    ap.add_argument("--no-faces", action="store_true")
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

    if a.no_faces:
        return
    fcpu, fgpu = FaceEngine(device="cpu"), FaceEngine(device=gpu_dev)
    for e in (fcpu, fgpu):
        e.index(files[0])  # calentamiento y carga de modelos
    f_cpu, t_cpu = timed(fcpu.index, files)
    print()
    print(f"Caras CPU (OpenCV) {t_cpu:6.2f} s/foto   ({sum(len(x) for x in f_cpu)} caras)")
    if fgpu.device == "cpu":
        print("Caras GPU          NO ACTIVA (ver avisos)")
        return
    f_gpu, t_gpu = timed(fgpu.index, files)
    print(f"Caras GPU ({fgpu.device:4s})   {t_gpu:6.2f} s/foto   x{t_cpu / t_gpu:.2f} más rápido   ({sum(len(x) for x in f_gpu)} caras)")
    same = sum(len(c) == len(g) for c, g in zip(f_cpu, f_gpu))
    sims = [max(float(ec @ eg) for _, _, eg in g) for c, g in zip(f_cpu, f_gpu) if g for _, _, ec in c]
    print(f"      mismo número de caras en CPU y GPU: {same}/{len(files)} fotos")
    if sims:
        print(f"      coseno CPU vs GPU de las mismas caras: mín {min(sims):.4f} · media {np.mean(sims):.4f} (debería ser ≈ 1,0)")


if __name__ == "__main__":
    main()
