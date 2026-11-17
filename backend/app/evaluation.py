"""Evaluación del OCR de dorsales contra etiquetas manuales.

Metodología (ver docs/EVALUATION.md):
 - Cada foto etiquetada recibe una partición determinista (por SHA-256): 30 % 'tune', 70 % 'test'.
 - Los parámetros solo se ajustan con 'tune'. 'test' es la validación final y cada ejecución queda registrada.
 - Las métricas se calculan sobre pares (foto, número): TP = predicho y etiquetado, FP = predicho y no etiquetado,
   FN = etiquetado y no predicho. Se informa por dorsal (instancia) y por fotografía.
"""
import json
import statistics
import threading
import time
import traceback

from .bibs import BibConfig, similar_numbers
from .imaging import original_path

TAGS = ["inclinado", "ocluido", "pequeno", "varios_corredores", "fondo_complejo", "cartel_reloj", "poca_luz", "desenfocado",
        # condiciones de las caras
        "cara_pequena", "perfil", "gafas", "gorra"]

EVAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS gt_labels(
  photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
  state TEXT NOT NULL,              -- labeled | no_bib (sin dorsal legible)
  bibs TEXT NOT NULL DEFAULT '[]',  -- JSON: dorsales realmente visibles y legibles
  present TEXT NOT NULL DEFAULT '[]', -- JSON: dorsales de corredores que SALEN en la foto aunque su dorsal no se lea
  tags TEXT NOT NULL DEFAULT '[]',
  split TEXT NOT NULL,              -- tune | test
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS eval_runs(
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  split TEXT NOT NULL,
  params TEXT NOT NULL,
  n_photos INTEGER NOT NULL,
  metrics TEXT NOT NULL,
  details TEXT NOT NULL
);
"""


def split_for(sha256: str) -> str:
    return "tune" if int(sha256[:8], 16) % 10 < 3 else "test"


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}


def compute_metrics(items):
    """items: [{id, truth:set[str], pred:set[str], tags:list, seconds:float}]. Función pura."""
    tp = fp = fn = 0
    errors = {"false_positives": [], "false_negatives": []}
    per_number = {}
    pos = [i for i in items if i["truth"]]
    neg = [i for i in items if not i["truth"]]
    photo_all = photo_any = photo_exact = 0
    neg_alarm = 0
    by_tag = {}
    for it in items:
        t, p = it["truth"], it["pred"]
        a, b, c = len(t & p), len(p - t), len(t - p)
        tp, fp, fn = tp + a, fp + b, fn + c
        for n in t:
            d = per_number.setdefault(n, [0, 0])
            d[0 if n in p else 1] += 1
        for n in p - t:
            near = any(similar_numbers(n, x) for x in t)
            errors["false_positives"].append({"photo_id": it["id"], "number": n, "near_miss_of_label": near})
        for n in t - p:
            errors["false_negatives"].append({"photo_id": it["id"], "number": n})
        if t:
            photo_all += t <= p
            photo_any += bool(t & p)
            photo_exact += t == p
        elif p:
            neg_alarm += 1
        for tag in it["tags"]:
            g = by_tag.setdefault(tag, [0, 0, 0, 0])
            g[0] += a; g[1] += b; g[2] += c; g[3] += 1
    times = [i["seconds"] for i in items if i.get("seconds") is not None]
    macro = [v[0] / (v[0] + v[1]) for v in per_number.values()]
    return {
        "photos": len(items), "photos_with_bibs": len(pos), "photos_without_readable_bib": len(neg),
        "per_bib": _prf(tp, fp, fn),   # un "dorsal detectado" = un par (foto, número)
        "per_bib_macro_recall": statistics.mean(macro) if macro else None,  # media sobre números distintos
        "per_photo": {
            "all_bibs_found": photo_all, "any_bib_found": photo_any, "exact_set": photo_exact,
            "all_bibs_found_rate": photo_all / len(pos) if pos else None,
            "any_bib_found_rate": photo_any / len(pos) if pos else None,
            "exact_set_rate": photo_exact / len(pos) if pos else None,
            "false_alarm_photos": neg_alarm,
            "false_alarm_rate": neg_alarm / len(neg) if neg else None,
        },
        "by_tag": {k: {"photos": v[3], **_prf(v[0], v[1], v[2])} for k, v in sorted(by_tag.items())},
        "timing": {
            "total_s": sum(times), "mean_s": statistics.mean(times) if times else None,
            "median_s": statistics.median(times) if times else None,
            "p95_s": sorted(times)[int(0.95 * (len(times) - 1))] if times else None,
        },
        "errors": errors,
    }


class EvalRunner:
    """Ejecuta una evaluación en un hilo propio y expone progreso real."""

    def __init__(self, db, settings, reader_factory, face_timer=None):
        self.db, self.settings, self.reader_factory = db, settings, reader_factory
        self.face_timer = face_timer  # callable(path) -> segundos, o None si el índice facial está desactivado
        self.state = {"running": False, "done": 0, "total": 0, "error": None, "run_id": None}
        self._lock = threading.Lock()

    def start(self, split, params):
        cfg = BibConfig.from_dict(params or {})
        with self._lock:
            if self.state["running"]:
                raise RuntimeError("Ya hay una evaluación en curso")
            self.state = {"running": True, "done": 0, "total": 0, "error": None, "run_id": None}
        threading.Thread(target=self._run, args=(split, cfg), daemon=True, name="eval").start()

    def _run(self, split, cfg):
        try:
            c = self.db.conn()
            rows = c.execute("SELECT p.id,p.sha256,p.ext,g.bibs,g.tags FROM gt_labels g JOIN photos p ON p.id=g.photo_id "
                             "WHERE g.split=? ORDER BY p.id", (split,)).fetchall()
            self.state["total"] = len(rows)
            reader = self.reader_factory(cfg)
            reader.ocr  # carga el modelo fuera del cronómetro
            items, face_times = [], []
            timer = self.face_timer() if self.face_timer else None
            t_all = time.perf_counter()
            for r in rows:
                path = original_path(self.settings, r["sha256"], r["ext"])
                t0 = time.perf_counter()
                dets = reader.read(path)
                dt = time.perf_counter() - t0
                items.append({"id": r["id"], "truth": set(json.loads(r["bibs"])), "pred": {d.number for d in dets},
                              "tags": json.loads(r["tags"]), "seconds": dt})
                if timer:
                    face_times.append(timer(path))
                self.state["done"] += 1
            m = compute_metrics(items)
            m["timing"]["wall_s"] = time.perf_counter() - t_all
            if face_times:
                m["timing"]["face_mean_s"] = statistics.mean(face_times)
                m["timing"]["face_total_s"] = sum(face_times)
            cur = c.execute("INSERT INTO eval_runs(split,params,n_photos,metrics,details) VALUES(?,?,?,?,?)",
                            (split, json.dumps(cfg.dict()), len(items), json.dumps(m), "[]"))
            self.state["run_id"] = cur.lastrowid
        except Exception as e:  # pragma: no cover
            traceback.print_exc()
            self.state["error"] = f"{type(e).__name__}: {e}"
        finally:
            self.state["running"] = False


# ---------------------------------------------------------------------------
# Evaluación de la BÚSQUEDA (lo que ve el usuario): por dorsal, por cara y combinada.

def ocr_items_from_db(conn, split=None):
    """Ítems para compute_metrics a partir de las lecturas ya guardadas (sin volver a ejecutar el OCR)."""
    q = "SELECT g.photo_id, g.bibs, g.tags FROM gt_labels g" + (" WHERE g.split=?" if split else "")
    items = []
    for r in conn.execute(q, (split,) if split else ()):
        pred = {d["number"] for d in conn.execute(
            "SELECT number FROM bib_detections WHERE photo_id=? AND review!='rejected'", (r["photo_id"],))}
        items.append({"id": r["photo_id"], "truth": set(json.loads(r["bibs"])), "pred": pred,
                      "tags": json.loads(r["tags"]), "seconds": None})
    return items


def evaluate_search(conn, split, doubtful_below, faces_available):
    """Para cada dorsal etiquetado, compara las fotos que devuelve RaceFinder con las fotos en las que ese corredor
    aparece de verdad (dorsal legible o no). Se evalúa solo sobre las fotos etiquetadas de la partición.
    La semilla facial se calcula exactamente como en la interfaz (caras preseleccionadas)."""
    from . import faces as facemod
    rows = conn.execute("SELECT photo_id, bibs, present, tags FROM gt_labels" + (" WHERE split=?" if split else ""),
                        (split,) if split else ()).fetchall()
    labeled = {r["photo_id"]: r for r in rows}
    truth, readable_truth = {}, {}
    for r in rows:
        bibs, present = set(json.loads(r["bibs"])), set(json.loads(r["present"]))
        for n in bibs | present:
            truth.setdefault(n, set()).add(r["photo_id"])
        for n in bibs:
            readable_truth.setdefault(n, set()).add(r["photo_id"])
    queries = sorted(n for n in truth if n in readable_truth)  # sin ningún dorsal legible no hay semilla posible
    modes = ["bib", "face", "combined"] if faces_available else ["bib"]
    acc = {m: [0, 0, 0] for m in modes}
    face_only_found = face_only_total = 0
    per_query, errors = [], []
    by_tag = {}
    for n in queries:
        t = truth[n]
        bib_pred = {d["photo_id"] for d in conn.execute(
            "SELECT DISTINCT photo_id FROM bib_detections WHERE number=? AND review!='rejected'", (n,))} & set(labeled)
        preds = {"bib": bib_pred}
        if faces_available:
            _, cands = facemod.candidates_for_bib(conn, n, doubtful_below)
            seeds = [f["id"] for f in cands if f["preselect"]]
            face_pred = set(facemod.search(conn, seeds)) & set(labeled) if seeds else set()
            preds["face"] = face_pred
            preds["combined"] = bib_pred | face_pred
            hidden = t - readable_truth[n]          # fotos en las que el corredor sale pero su dorsal no se lee
            face_only_total += len(hidden)
            face_only_found += len(hidden & face_pred)
        row = {"bib": n, "truth": len(t)}
        for m in modes:
            p = preds[m]
            tp, fp, fn = len(p & t), len(p - t), len(t - p)
            acc[m][0] += tp; acc[m][1] += fp; acc[m][2] += fn
            row[m] = {"tp": tp, "fp": fp, "fn": fn}
            for pid in p - t:
                errors.append({"mode": m, "bib": n, "photo_id": pid, "type": "fp"})
            for pid in t - p:
                errors.append({"mode": m, "bib": n, "photo_id": pid, "type": "fn"})
            for pid in t | p:
                for tag in json.loads(labeled[pid]["tags"]):
                    g = by_tag.setdefault(m, {}).setdefault(tag, [0, 0, 0])
                    g[0] += pid in p and pid in t; g[1] += pid in p and pid not in t; g[2] += pid in t and pid not in p
        per_query.append(row)
    return {
        "kind": "search", "photos": len(rows), "queries": len(queries), "modes": modes,
        "per_mode": {m: _prf(*acc[m]) for m in modes},
        "face_only_recall": (face_only_found / face_only_total) if face_only_total else None,
        "face_only_pairs": face_only_total,
        "by_tag": {m: {k: _prf(*v) for k, v in sorted(g.items())} for m, g in by_tag.items()},
        "per_query": per_query,
        "errors": errors[:500],
    }
