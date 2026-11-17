"""Compara CPU y GPU en tus fotos, y el redimensionado rápido, comprobando que dan los mismos resultados.

Uso (desde la raíz del repositorio):
    backend\\.venv\\Scripts\\python.exe backend\\tools\\gpu_bench.py CARPETA_O_FOTOS... [--n 30] [--device cuda|dml|auto]
                                                                  [--no-faces] [--no-fast]

Qué mide (mismas fotos, tras un calentamiento que no cuenta):
  1. OCR de dorsales: CPU frente a GPU, y que lean los mismos dorsales.
  2. Caras (YuNet + SFace): OpenCV en CPU frente a ONNX Runtime en GPU, y que den las mismas caras y vectores.
  3. Redimensionado rápido (RACEFINDER_FAST_RESIZE): mismo motor con y sin él, y que no cambien dorsales ni caras.
Si la GPU no se activa de verdad, lo dice (ONNX Runtime vuelve a CPU en silencio si faltan librerías).
"""
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from app import resize
from app.bibs import BibReader
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


def same_bibs(a, b):
    return sum({d.number for d in x} == {d.number for d in y} for x, y in zip(a, b))


def face_report(ref, other, n):
    same = sum(len(c) == len(g) for c, g in zip(ref, other))
    sims = [max(float(ec @ eg) for _, _, eg in g) for c, g in zip(ref, other) if g for _, _, ec in c]
    print(f"      mismo número de caras: {same}/{n} fotos")
    if sims:
        print(f"      coseno de las mismas caras: mín {min(sims):.4f} · media {np.mean(sims):.4f} (debería ser cercano a 1,0)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--n", type=int, default=30, help="número máximo de fotos (repartidas por la carpeta)")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "dml"])
    ap.add_argument("--no-faces", action="store_true")
    ap.add_argument("--no-fast", action="store_true", help="omite la comparación del redimensionado rápido")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    resize.set_fast(False)  # todo lo anterior a la sección 3 se mide con el redimensionado de siempre

    files = collect(a.paths, a.n)
    n = len(files)
    print(f"{n} fotos · proveedores ONNX: {onnx_providers()}\n")

    # ---------------- 1. OCR ----------------
    gpu_dev = resolve_ocr_device(a.device)
    cpu, gpu = BibReader(device="cpu"), BibReader(device=gpu_dev)
    gpu.ocr  # carga y comprueba el proveedor real
    gpu_dev = gpu.device
    for r in (cpu, gpu):
        r.read(files[0])  # calentamiento (en CUDA la primera pasada compila kernels)
    res_cpu, t_cpu = timed(cpu.read, files)
    print(f"OCR   CPU        {t_cpu:6.2f} s/foto")
    best_reader, res_best = cpu, res_cpu
    if gpu_dev == "cpu":
        print("OCR   GPU        NO ACTIVA: ONNX Runtime no ofrece GPU (instala backend/requirements-gpu.txt) o no pudo cargarla (ver avisos)")
    else:
        res_gpu, t_gpu = timed(gpu.read, files)
        print(f"OCR   GPU ({gpu_dev:4s}) {t_gpu:6.2f} s/foto   x{t_cpu / t_gpu:.2f} más rápido")
        print(f"      mismos dorsales en CPU y GPU: {same_bibs(res_cpu, res_gpu)}/{n} fotos "
              f"({sum(len(c) for c in res_cpu)} lecturas CPU, {sum(len(g) for g in res_gpu)} GPU)")
        best_reader, res_best, t_best_ocr = gpu, res_gpu, t_gpu

    # ---------------- 2. Caras ----------------
    best_faces, f_best, t_best_faces = None, None, None
    if not a.no_faces:
        fcpu, fgpu = FaceEngine(device="cpu"), FaceEngine(device=gpu_dev)
        for e in (fcpu, fgpu):
            e.index(files[0])  # calentamiento y carga de modelos
        f_cpu, t_cpu_f = timed(fcpu.index, files)
        print(f"\nCaras CPU (OpenCV) {t_cpu_f:6.2f} s/foto   ({sum(len(x) for x in f_cpu)} caras)")
        best_faces, f_best, t_best_faces = fcpu, f_cpu, t_cpu_f
        if fgpu.device == "cpu":
            print("Caras GPU          NO ACTIVA (ver avisos)")
        else:
            f_gpu, t_gpu_f = timed(fgpu.index, files)
            print(f"Caras GPU ({fgpu.device:4s})   {t_gpu_f:6.2f} s/foto   x{t_cpu_f / t_gpu_f:.2f} más rápido   "
                  f"({sum(len(x) for x in f_gpu)} caras)")
            face_report(f_cpu, f_gpu, n)
            best_faces, f_best, t_best_faces = fgpu, f_gpu, t_gpu_f

    # ---------------- 3. Redimensionado rápido ----------------
    if a.no_fast:
        return
    where = gpu_dev if gpu_dev != "cpu" else "CPU"
    print(f"\n--- Redimensionado rápido (RACEFINDER_FAST_RESIZE=1), medido en {where} ---")
    resize.set_fast(True)
    try:
        res_fast, t_fast = timed(best_reader.read, files)
        t_ref = t_best_ocr if gpu_dev != "cpu" else t_cpu
        print(f"OCR   {t_ref:5.2f} -> {t_fast:5.2f} s/foto   x{t_ref / t_fast:.2f}")
        print(f"      mismos dorsales con y sin él: {same_bibs(res_best, res_fast)}/{n} fotos "
              f"({sum(len(c) for c in res_best)} lecturas antes, {sum(len(g) for g in res_fast)} después)")
        if best_faces is not None:
            f_fast, t_fast_f = timed(best_faces.index, files)
            print(f"Caras {t_best_faces:5.2f} -> {t_fast_f:5.2f} s/foto   x{t_best_faces / t_fast_f:.2f}")
            face_report(f_best, f_fast, n)
    finally:
        resize.set_fast(None)


if __name__ == "__main__":
    main()
