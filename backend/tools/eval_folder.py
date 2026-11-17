"""Evaluación con una carpeta de fotos REALES etiquetadas a mano.

1) Crear la plantilla de etiquetas (no sobrescribe una existente):
     .venv\\Scripts\\python.exe tools\\eval_folder.py plantilla "D:\\fotos\\maraton"
   Rellena racefinder-etiquetas.json en esa carpeta:
     "IMG_0012.jpg": {"bibs": ["184"], "present": ["77"], "tags": ["gorra"]}
       bibs    = dorsales que una persona puede LEER en la foto
       present = corredores que SALEN en la foto aunque su dorsal no se lea (para medir la búsqueda por cara)
       tags    = condiciones opcionales (ver TAGS en app/evaluation.py)
   Las fotos sin entrada no se evalúan. Una entrada con bibs y present vacíos = foto sin corredores identificables.

2) Evaluar (importa en una biblioteca aislada, lee dorsales y, si se pide, caras; genera el informe):
     .venv\\Scripts\\python.exe tools\\eval_folder.py evaluar "D:\\fotos\\maraton" [--caras --consiento]

Las fotos nunca salen del equipo y los originales no se modifican (se copian byte a byte a la biblioteca aislada).
Las métricas de 'test' son la validación final: no ajustes parámetros mirándolas (usa 'tune').
"""
import argparse
import hashlib
import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import imaging  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.evaluation import TAGS, compute_metrics, evaluate_search, ocr_items_from_db, split_for  # noqa: E402
from app.worker import Worker  # noqa: E402

LABELS = "racefinder-etiquetas.json"
EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def images(folder: Path):
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in EXTS and ".racefinder" not in p.parts)


def plantilla(folder: Path):
    out = folder / LABELS
    if out.exists():
        print(f"Ya existe {out}; no se sobrescribe.")
        return
    data = {"_ayuda": {"bibs": "dorsales legibles", "present": "corredores que salen sin dorsal legible",
                       "tags": TAGS, "nota": "borra las entradas de fotos que no quieras evaluar"}}
    for p in images(folder):
        data[p.relative_to(folder).as_posix()] = {"bibs": [], "present": [], "tags": []}
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Plantilla con {len(data) - 1} fotos: {out}")


def fmt(x, pct=True):
    return "—" if x is None else (f"{x * 100:.1f} %" if pct else f"{x:.2f}")


def evaluar(folder: Path, caras: bool, data_dir: Path):
    labels_path = folder / LABELS
    if not labels_path.exists():
        sys.exit(f"Falta {labels_path}. Créala con: eval_folder.py plantilla \"{folder}\"")
    labels = {k: v for k, v in json.loads(labels_path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    settings = Settings(data_dir)
    settings.ensure()
    db = Database(settings.db_path)
    c = db.conn()
    worker = Worker(db, settings, faces_enabled=lambda: caras)

    # 1) importación (byte a byte; los duplicados se reutilizan)
    ids = {}
    for p in images(folder):
        rel = p.relative_to(folder).as_posix()
        if rel not in labels:
            continue
        with open(p, "rb") as f:
            meta = imaging.ingest(settings, f, p.name)
        row = c.execute("SELECT id FROM photos WHERE sha256=?", (meta["sha256"],)).fetchone()
        imaging.commit_original(settings, meta)
        if row:
            ids[rel] = row["id"]
        else:
            imaging.make_thumb(settings, meta["sha256"], meta["ext"])
            ids[rel] = c.execute("INSERT INTO photos(sha256,original_name,ext,size,width,height) VALUES(?,?,?,?,?,?)",
                                 (meta["sha256"], rel, meta["ext"], meta["size"], meta["width"], meta["height"])).lastrowid
    missing = sorted(set(labels) - set(ids))
    print(f"Fotos etiquetadas importadas: {len(ids)}" + (f" · no encontradas: {len(missing)}" if missing else ""))

    # 2) etiquetas -> gt_labels (se rehacen en cada ejecución)
    c.execute("DELETE FROM gt_labels")
    for rel, pid in ids.items():
        lab = labels[rel]
        bibs = sorted({str(b) for b in lab.get("bibs", [])})
        present = sorted({str(b) for b in lab.get("present", [])} - set(bibs))
        bad = [b for b in bibs + present if not b.isdigit() or len(b) > 5] + [t for t in lab.get("tags", []) if t not in TAGS]
        if bad:
            sys.exit(f"Etiqueta inválida en {rel}: {bad}")
        sha = c.execute("SELECT sha256 FROM photos WHERE id=?", (pid,)).fetchone()[0]
        c.execute("INSERT INTO gt_labels(photo_id,state,bibs,present,tags,split) VALUES(?,?,?,?,?,?)",
                  (pid, "labeled" if bibs else "no_bib", json.dumps(bibs), json.dumps(present),
                   json.dumps(sorted(set(lab.get("tags", [])))), split_for(sha)))

    # 3) procesamiento con tiempos reales (lo ya procesado en ejecuciones anteriores no se repite)
    def drain(step, label):
        times = []
        while True:
            t0 = time.perf_counter()
            if not step():
                break
            times.append(time.perf_counter() - t0)
            print(f"\r{label}: {len(times)}", end="", flush=True)
        if times:
            print()
        return times

    ocr_t = drain(worker._process_one, "Leyendo dorsales")
    face_t = drain(worker._process_face, "Analizando caras") if caras else []
    if caras and worker.face_error:
        print("AVISO:", worker.face_error)

    # 4) métricas por partición
    report = {"carpeta": str(folder), "fotos_etiquetadas": len(ids), "caras": caras,
              "tiempos": {"ocr_fotos_medidas": len(ocr_t), "ocr_medio_s": statistics.mean(ocr_t) if ocr_t else None,
                          "ocr_total_s": sum(ocr_t), "caras_fotos_medidas": len(face_t),
                          "caras_medio_s": statistics.mean(face_t) if face_t else None, "caras_total_s": sum(face_t)},
              "particiones": {}}
    for split in ("tune", "test"):
        n = c.execute("SELECT COUNT(*) FROM gt_labels WHERE split=?", (split,)).fetchone()[0]
        if not n:
            continue
        ocr = compute_metrics(ocr_items_from_db(c, split))
        ocr.pop("errors", None)
        search = evaluate_search(c, split, settings.doubtful_below, caras)
        report["particiones"][split] = {"fotos": n, "ocr": ocr, "busqueda": search}
    c.execute("INSERT INTO settings(key,value) VALUES('faces_enabled',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              ("True" if caras else "False",))

    out_json = data_dir / "informe-evaluacion.json"
    out_json.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    md = [f"# Evaluación RaceFinder\n\nCarpeta: `{folder}` · fotos etiquetadas: {len(ids)} · caras: {'sí' if caras else 'no'}\n"]
    t = report["tiempos"]
    md.append(f"Tiempo OCR: medio {fmt(t['ocr_medio_s'], False)} s/foto sobre {t['ocr_fotos_medidas']} fotos procesadas en esta ejecución"
              f" · caras: medio {fmt(t['caras_medio_s'], False)} s/foto ({t['caras_fotos_medidas']} fotos)\n")
    for split, r in report["particiones"].items():
        o, s = r["ocr"], r["busqueda"]
        md.append(f"\n## Partición `{split}` ({r['fotos']} fotos){' — VALIDACIÓN FINAL' if split == 'test' else ' — solo para ajustar'}\n")
        if r["fotos"] < 30:
            md.append(f"> Muestra pequeña ({r['fotos']} fotos): cifras orientativas.\n")
        b = o["per_bib"]
        md.append(f"**OCR por dorsal (foto, número):** precision {fmt(b['precision'])} · recall {fmt(b['recall'])} · F1 {fmt(b['f1'])} "
                  f"(TP {b['tp']}, FP {b['fp']}, FN {b['fn']})  \n")
        pp = o["per_photo"]
        md.append(f"**OCR por foto:** todos los dorsales {fmt(pp['all_bibs_found_rate'])} · al menos uno {fmt(pp['any_bib_found_rate'])} · "
                  f"falsas alarmas en fotos sin dorsal {pp['false_alarm_photos']}/{o['photos_without_readable_bib']}\n")
        md.append(f"\n**Búsqueda** ({s['queries']} dorsales consultados):\n\n| Modo | Precision | Recall | F1 | TP | FP | FN |\n|---|---|---|---|---|---|---|")
        for m in s["modes"]:
            x = s["per_mode"][m]
            md.append(f"| {dict(bib='Solo dorsal', face='Solo cara', combined='Dorsal o cara')[m]} | {fmt(x['precision'])} | {fmt(x['recall'])} | {fmt(x['f1'])} | {x['tp']} | {x['fp']} | {x['fn']} |")
        if s["face_only_recall"] is not None:
            md.append(f"\nFotos en las que el corredor sale **sin dorsal legible** recuperadas por la cara: {fmt(s['face_only_recall'])} de {s['face_only_pairs']}\n")
        if o["by_tag"]:
            md.append("\n| Condición (OCR) | Fotos | Precision | Recall |\n|---|---|---|---|")
            for k, v in o["by_tag"].items():
                md.append(f"| {k} | {v['photos']} | {fmt(v['precision'])} | {fmt(v['recall'])} |")
        if "face" in s.get("by_tag", {}):
            md.append("\n| Condición (cara) | Precision | Recall | TP | FP | FN |\n|---|---|---|---|---|---|")
            for k, v in s["by_tag"]["face"].items():
                md.append(f"| {k} | {fmt(v['precision'])} | {fmt(v['recall'])} | {v['tp']} | {v['fp']} | {v['fn']} |")
    md.append("\nLa similitud facial es un coseno, no una probabilidad. Los errores concretos están en el JSON (`errors`).\n")
    out_md = data_dir / "informe-evaluacion.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"\nInforme: {out_md}\nPara revisar los fallos en la web: $env:RACEFINDER_DATA=\"{data_dir}\"; pnpm run dev")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("accion", choices=["plantilla", "evaluar"])
    ap.add_argument("carpeta")
    ap.add_argument("--caras", action="store_true", help="evaluar también la búsqueda por cara")
    ap.add_argument("--consiento", action="store_true", help="confirmo que tengo permiso para procesar las caras de estas fotos")
    ap.add_argument("--datos", help="carpeta de la biblioteca aislada (por defecto data_eval/<nombre>)")
    a = ap.parse_args()
    folder = Path(a.carpeta).resolve()
    if not folder.is_dir():
        sys.exit(f"No existe la carpeta {folder}")
    if a.accion == "plantilla":
        plantilla(folder)
    else:
        if a.caras and not a.consiento:
            sys.exit("Procesar caras requiere --consiento (permiso para tratar datos biométricos de esas fotos).")
        tag = hashlib.sha256(str(folder).encode()).hexdigest()[:8]
        data_dir = Path(a.datos).resolve() if a.datos else ROOT.parent / "data_eval" / f"{folder.name}-{tag}"
        evaluar(folder, a.caras, data_dir)
