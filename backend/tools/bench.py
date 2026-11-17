"""Evalua una configuracion de BibReader sobre una carpeta con labels.json (formato de tools/synth.py
o de un conjunto real: {"foto.jpg": {"bibs": [...], "tags": [...], "cond": "..."}}).
Uso: python tools/bench.py <carpeta> [--set min_conf=0.6 --set tile_trigger=0] [--out resultado.json]
Imprime metricas por dorsal y por foto, desglose por condicion, tiempos y memoria maxima.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.bibs import BibConfig, BibReader  # noqa: E402
from app.evaluation import compute_metrics  # noqa: E402


def rss_mb():
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("a", ctypes.c_size_t), ("b", ctypes.c_size_t),
                        ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC(); pmc.cb = ctypes.sizeof(pmc)
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return pmc.PeakWorkingSetSize / 1e6
    except Exception:
        return None


def run(folder: Path, params: dict, reader=None, only=None):
    labels = json.loads((folder / "labels.json").read_text(encoding="utf-8"))
    cfg = BibConfig.from_dict(params)
    reader = reader.with_config(cfg) if reader else BibReader(cfg)
    reader.ocr
    items = []
    t_all = time.perf_counter()
    for name, lab in sorted(labels.items()):
        if only and not name.startswith(only):
            continue
        t0 = time.perf_counter()
        dets = reader.read(folder / name)
        items.append({"id": name, "truth": set(lab["bibs"]), "pred": {d.number for d in dets},
                      "tags": [lab["cond"]] if lab.get("cond") else lab.get("tags", []), "seconds": time.perf_counter() - t0})
    m = compute_metrics(items)
    m["timing"]["wall_s"] = time.perf_counter() - t_all
    m["peak_rss_mb"] = rss_mb()
    return m, cfg


def show(m, cfg):
    b, p, t = m["per_bib"], m["per_photo"], m["timing"]
    f = lambda x: "n/a" if x is None else f"{x:.3f}"
    print(f"config: {cfg.dict()}")
    print(f"fotos={m['photos']}  por dorsal: P={f(b['precision'])} R={f(b['recall'])} F1={f(b['f1'])} "
          f"(TP={b['tp']} FP={b['fp']} FN={b['fn']})")
    print(f"por foto: todos los dorsales encontrados={f(p['all_bibs_found_rate'])}  falsas alarmas en fotos sin dorsal={p['false_alarm_photos']}/{m['photos_without_readable_bib']}")
    print(f"tiempo: medio={f(t['mean_s'])}s mediana={f(t['median_s'])}s p95={f(t['p95_s'])}s total={f(t['total_s'])}s  pico RAM={m['peak_rss_mb'] and round(m['peak_rss_mb'])}MB")
    print("por condicion:")
    for k, v in m["by_tag"].items():
        print(f"  {k:18s} n={v['photos']:3d} P={f(v['precision'])} R={f(v['recall'])} TP={v['tp']} FP={v['fp']} FN={v['fn']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--set", action="append", default=[], help="parametro=valor de BibConfig")
    ap.add_argument("--out")
    a = ap.parse_args()
    params = dict(s.split("=", 1) for s in a.set)
    m, cfg = run(Path(a.folder), params)
    show(m, cfg)
    if a.out:
        Path(a.out).write_text(json.dumps({"params": cfg.dict(), "metrics": m}, indent=1), encoding="utf-8")
