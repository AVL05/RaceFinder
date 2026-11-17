"""API REST de RaceFinder. Solo escucha en localhost por defecto (ver run.ps1)."""
import errno
import json
import os
import subprocess
import sys
import time

import numpy as np
import re
import shutil
import sqlite3
import uuid
import zipfile
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import faces as facemod
from . import imaging
from .bibs import BibConfig, similar_numbers
from .config import Settings
from .importer import ImportJob
from .evaluation import EvalRunner, TAGS, evaluate_search, split_for
from .db import Database
from .worker import Worker

BIB_RE = re.compile(r"^\d{1,5}$")
MIN_FREE_BYTES = 2 * 1024 ** 3   # por debajo, no se aceptan más fotos


class ExportRequest(BaseModel):
    ids: List[int] = Field(min_length=1, max_length=20000)


class IdsBody(BaseModel):
    ids: List[int] = Field(min_length=1, max_length=20000)


class ImportFolderBody(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


class PickFolderBody(BaseModel):
    title: str = Field("Elige una carpeta", max_length=120)


class SaveBody(BaseModel):
    ids: List[int] = Field(min_length=1, max_length=20000)
    dest: str = Field(min_length=1, max_length=1000)
    subfolder: str = Field("", max_length=80)   # p. ej. "dorsal-123": una carpeta por corredor
    open_after: bool = True


class ManualBib(BaseModel):
    number: str


MODES = {"fast": "nunca", "balanced": "si_vacio", "thorough": "siempre"}


class SettingsBody(BaseModel):
    mode: str = "balanced"           # fast | balanced | thorough
    min_number: int = Field(0, ge=0, le=99999)
    max_number: int = Field(99999, ge=0, le=99999)
    faces_enabled: bool = False
    face_consent: bool = False       # obligatorio para activar el reconocimiento facial


class FaceSearchBody(BaseModel):
    face_ids: List[int] = Field(min_length=1, max_length=200)


class LabelBody(BaseModel):
    state: str                       # labeled | no_bib
    bibs: List[str] = []
    present: List[str] = []          # corredores que salen aunque su dorsal no se lea
    tags: List[str] = []


class EvalRunBody(BaseModel):
    split: str                       # tune | test
    params: dict = {}
    confirm_test: bool = False


class ReviewBody(BaseModel):
    review: str  # confirmed | rejected | auto


def create_app(settings: Settings = None, reader=None, start_worker=True) -> FastAPI:
    settings = settings or Settings()
    settings.ensure()
    db = Database(settings.db_path)
    def faces_on():
        r = db.conn().execute("SELECT value FROM settings WHERE key='faces_enabled'").fetchone()
        return bool(r) and r["value"] == "True"

    worker = Worker(db, settings, reader=reader, faces_enabled=faces_on)

    def load_settings():
        rows = {r["key"]: r["value"] for r in db.conn().execute("SELECT * FROM settings")}
        return {"mode": rows.get("mode", "balanced"), "min_number": int(rows.get("min_number", 0)),
                "max_number": int(rows.get("max_number", 99999)), "faces_enabled": rows.get("faces_enabled") == "True",
                "faces_consent_at": rows.get("faces_consent_at")}

    def apply_mode(mode):
        worker.reader = worker.reader.with_config(BibConfig.from_dict({"tile_policy": MODES[mode]}))

    apply_mode(load_settings()["mode"])
    def face_timer():
        if not faces_on() or not facemod.models_ready(worker.face_engine.models_dir):
            return None
        def t(path):
            t0 = time.perf_counter()
            worker.face_engine.index(path)
            return time.perf_counter() - t0
        return t

    evaluator = EvalRunner(db, settings, lambda cfg: worker.reader.with_config(cfg), face_timer=face_timer)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            worker.start()
        yield
        worker.stop()
        for p in settings.tmp.glob("*.part"):  # limpieza de temporales
            p.unlink(missing_ok=True)

    app = FastAPI(title="RaceFinder", version="0.1.0", lifespan=lifespan)
    app.state.settings, app.state.db, app.state.worker = settings, db, worker
    app.state.evaluator = evaluator
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type"])

    def photo_row(r, bibs=None):
        d = {"id": r["id"], "v": r["sha256"][:12], "name": r["original_name"], "size": r["size"], "width": r["width"], "height": r["height"],
             "ocr_status": r["ocr_status"], "ocr_error": r["ocr_error"], "added_at": r["added_at"]}
        if bibs is not None:
            d["bibs"] = bibs
        return d

    def bibs_for(ids):
        if not ids:
            return {}
        q = ",".join("?" * len(ids))
        out = {i: [] for i in ids}
        cfg = load_settings()
        for b in db.conn().execute(
                f"SELECT * FROM bib_detections WHERE photo_id IN ({q}) AND review!='rejected' "
                f"AND (review='manual' OR CAST(number AS INTEGER) BETWEEN ? AND ?) ORDER BY confidence DESC",
                (*ids, cfg["min_number"], cfg["max_number"])):
            out[b["photo_id"]].append({"id": b["id"], "number": b["number"], "confidence": b["confidence"],
                                       "bbox": json.loads(b["bbox"]), "review": b["review"]})
        return out

    def get_photo(pid):
        r = db.conn().execute("SELECT * FROM photos WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "Foto no encontrada")
        return r

    @app.get("/api/health")
    def health():
        return {"status": "ok", "ocr_engine": worker.reader.engine_name, "ocr_device": worker.reader.device,
                "face_device": worker.face_engine.device,
                "workers": worker.n_workers, "workers_auto": worker.workers_auto}

    @app.get("/api/stats")
    def stats():
        c = db.conn()
        total = c.execute("SELECT COUNT(*) n, COALESCE(SUM(size),0) s FROM photos").fetchone()
        by = {r["ocr_status"]: r["n"] for r in c.execute("SELECT ocr_status, COUNT(*) n FROM photos GROUP BY ocr_status")}
        cfg = load_settings()
        rng = (cfg["min_number"], cfg["max_number"])
        nb = c.execute("SELECT COUNT(DISTINCT number) n FROM bib_detections WHERE review!='rejected' AND "
                       "(review='manual' OR CAST(number AS INTEGER) BETWEEN ? AND ?)", rng).fetchone()["n"]
        wb = c.execute("SELECT COUNT(DISTINCT photo_id) n FROM bib_detections WHERE review!='rejected' AND "
                       "(review='manual' OR CAST(number AS INTEGER) BETWEEN ? AND ?)", rng).fetchone()["n"]
        fby = {r["face_status"]: r["n"] for r in c.execute("SELECT face_status, COUNT(*) n FROM photos GROUP BY face_status")}
        faces = {"enabled": cfg["faces_enabled"], "status": fby, "error": worker.face_error,
                 "count": c.execute("SELECT COUNT(*) FROM faces").fetchone()[0]}
        try:
            disk_free = shutil.disk_usage(settings.data_dir).free
        except OSError:
            disk_free = None
        return {"photos": total["n"], "bytes": total["s"], "ocr": by, "distinct_bibs": nb, "with_bib": wb,
                "processing_paused": worker.is_paused(), "current": worker.current, "faces": faces,
                "worker_alive": worker.alive(), "worker_error": worker.last_error, "disk_free": disk_free}

    @app.post("/api/photos")
    def upload(files: List[UploadFile] = File(...)):
        results = []
        c = db.conn()
        if shutil.disk_usage(settings.data_dir).free < MIN_FREE_BYTES:
            raise HTTPException(507, "Queda poco espacio en el disco. Libera espacio y vuelve a añadir la carpeta: las fotos ya importadas se omitirán.")
        for f in files:
            name = imaging.safe_name(f.filename)
            try:
                meta = imaging.ingest(settings, f.file, f.filename)
            except imaging.InvalidImage as e:
                results.append({"name": name, "status": "rejected", "error": str(e)})
                continue
            except OSError as e:
                if e.errno == errno.ENOSPC:
                    raise HTTPException(507, "El disco se ha llenado. Libera espacio y vuelve a añadir la carpeta.")
                results.append({"name": name, "status": "rejected", "error": f"{type(e).__name__}"})
                continue
            except Exception as e:  # un archivo problemático no debe tumbar el lote entero
                results.append({"name": name, "status": "rejected", "error": f"{type(e).__name__}"})
                continue
            row = c.execute("SELECT id FROM photos WHERE sha256=?", (meta["sha256"],)).fetchone()
            if row:
                imaging.commit_original(settings, meta)  # descarta el tmp
                results.append({"name": name, "status": "duplicate", "id": row["id"]})
                continue
            created = False
            try:
                created = imaging.commit_original(settings, meta)
                imaging.make_thumb(settings, meta["sha256"], meta["ext"])
                cur = c.execute(
                    "INSERT INTO photos(sha256,original_name,ext,size,width,height,head_hash) VALUES(?,?,?,?,?,?,?)",
                    (meta["sha256"], name, meta["ext"], meta["size"], meta["width"], meta["height"], meta["head"]))
                results.append({"name": name, "status": "added", "id": cur.lastrowid})
            except sqlite3.IntegrityError:
                results.append({"name": name, "status": "duplicate"})
            except Exception as e:
                if created:  # sin fila en la BD no hay quien lo borre: se limpia para no acumular huérfanos
                    imaging.original_path(settings, meta["sha256"], meta["ext"]).unlink(missing_ok=True)
                    imaging.thumb_path(settings, meta["sha256"]).unlink(missing_ok=True)
                results.append({"name": name, "status": "rejected", "error": f"{type(e).__name__}"})
        worker.kick()
        return {"results": results}

    RANGE_SQL = "(d.review='manual' OR CAST(d.number AS INTEGER) BETWEEN ? AND ?)"

    @app.get("/api/photos")
    def list_photos(limit: int = 200, offset: int = 0, status: str = "", filter: str = "all"):
        """filter: all | with_bib | no_bib | pending | error"""
        limit = max(1, min(limit, 1000))
        cfg = load_settings()
        rng = (cfg["min_number"], cfg["max_number"])
        has_bib = (f"EXISTS(SELECT 1 FROM bib_detections d WHERE d.photo_id=photos.id AND d.review!='rejected' AND {RANGE_SQL})")
        where, args = [], []
        if status in ("pending", "processing", "done", "error"):
            where.append("ocr_status=?"); args.append(status)
        if filter == "with_bib":
            where.append(has_bib); args += rng
        elif filter == "no_bib":
            where.append(f"ocr_status='done' AND NOT {has_bib}"); args += rng
        elif filter == "pending":
            where.append("ocr_status IN ('pending','processing')")
        elif filter == "error":
            where.append("ocr_status='error'")
        w = (" WHERE " + " AND ".join(where)) if where else ""
        c = db.conn()
        total = c.execute(f"SELECT COUNT(*) FROM photos{w}", args).fetchone()[0]
        rows = c.execute(f"SELECT * FROM photos{w} ORDER BY id DESC LIMIT ? OFFSET ?", (*args, limit, max(0, offset))).fetchall()
        b = bibs_for([r["id"] for r in rows])
        return {"photos": [photo_row(r, b[r["id"]]) for r in rows], "total": total}

    @app.get("/api/bibs/index")
    def bib_index(limit: int = 300):
        """Dorsales detectados con su número de fotos: para explorar sin saber qué buscar."""
        cfg = load_settings()
        rows = db.conn().execute(
            f"SELECT d.number, COUNT(DISTINCT d.photo_id) n, MAX(d.confidence) best FROM bib_detections d "
            f"WHERE d.review!='rejected' AND {RANGE_SQL} GROUP BY d.number ORDER BY CAST(d.number AS INTEGER) LIMIT ?",
            (cfg["min_number"], cfg["max_number"], max(1, min(limit, 2000)))).fetchall()
        return {"bibs": [{"number": r["number"], "photos": r["n"], "best": r["best"]} for r in rows]}

    @app.get("/api/bibs/{bid}/crop")
    def bib_crop(bid: int):
        b = db.conn().execute("SELECT d.bbox, p.sha256, p.ext FROM bib_detections d JOIN photos p ON p.id=d.photo_id "
                              "WHERE d.id=?", (bid,)).fetchone()
        if not b:
            raise HTTPException(404, "Detección no encontrada")
        path = imaging.make_crop(settings, b["sha256"], b["ext"], json.loads(b["bbox"]))
        if path is None:
            raise HTTPException(404, "Sin región (dorsal añadido a mano)")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})  # los id pueden reutilizarse

    @app.get("/api/photos/{pid}")
    def photo_detail(pid: int):
        r = get_photo(pid)
        return photo_row(r, bibs_for([pid])[pid])

    @app.get("/api/photos/{pid}/thumb")
    def thumb(pid: int):
        r = get_photo(pid)
        p = imaging.make_thumb(settings, r["sha256"], r["ext"])
        return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})

    @app.get("/api/photos/{pid}/preview")
    def preview(pid: int):
        r = get_photo(pid)
        p = imaging.make_preview(settings, r["sha256"], r["ext"])
        return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})

    @app.get("/api/photos/{pid}/original")
    def original(pid: int, download: bool = False):
        r = get_photo(pid)
        p = imaging.original_path(settings, r["sha256"], r["ext"])
        mt = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[r["ext"]]
        return FileResponse(p, media_type=mt, filename=r["original_name"] if download else None,
                            content_disposition_type="attachment" if download else "inline",
                            headers={"Cache-Control": "private, max-age=31536000, immutable"})

    def remove_files(r):
        imaging.original_path(settings, r["sha256"], r["ext"]).unlink(missing_ok=True)
        imaging.thumb_path(settings, r["sha256"]).unlink(missing_ok=True)
        imaging.preview_path(settings, r["sha256"]).unlink(missing_ok=True)
        for c in (settings.crops / r["sha256"][:2]).glob(f"{r['sha256']}_*.jpg"):
            c.unlink(missing_ok=True)

    def remove_photos(rows):
        """Un solo COMMIT para todas (con 20.000 fotos, uno por foto tardaría minutos); los archivos, después."""
        c = db.conn()
        c.execute("BEGIN")
        try:
            for r in rows:
                c.execute("DELETE FROM photos WHERE id=?", (r["id"],))
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
        for r in rows:
            remove_files(r)

    @app.delete("/api/photos/{pid}")
    def delete_photo(pid: int):
        remove_photos([get_photo(pid)])
        return {"deleted": pid}

    @app.post("/api/photos/delete")
    def delete_many(body: IdsBody):
        ids = list(dict.fromkeys(body.ids))
        rows = []
        for k in range(0, len(ids), 500):
            chunk = ids[k:k + 500]
            rows += db.conn().execute(f"SELECT * FROM photos WHERE id IN ({','.join('?' * len(chunk))})", chunk).fetchall()
        remove_photos(rows)
        return {"deleted": len(rows)}

    class Fingerprint(BaseModel):
        size: int
        head: str = Field(pattern=r"^[0-9a-f]{64}$")

    class KnownBody(BaseModel):
        items: List[Fingerprint] = Field(max_length=5000)

    @app.post("/api/photos/known")
    def photos_known(body: KnownBody):
        """¿Cuáles de estas fotos ya están? (tamaño + SHA-256 de los primeros 64 KB, calculado en el navegador).
        Permite reanudar una importación de miles de fotos sin volver a enviar las que ya se subieron."""
        c = db.conn()
        known = set()
        pairs = list({(i.size, i.head) for i in body.items})
        for k in range(0, len(pairs), 400):
            chunk = pairs[k:k + 400]
            where = " OR ".join(["(size=? AND head_hash=?)"] * len(chunk))
            for r in c.execute(f"SELECT size, head_hash FROM photos WHERE {where}", [v for p in chunk for v in p]):
                known.add((r["size"], r["head_hash"]))
        return {"known": [(i.size, i.head) in known for i in body.items]}

    def backfill_fingerprints():
        """Fotos importadas antes de existir la huella: se calcula leyendo 64 KB de cada original."""
        c = db.conn()
        rows = c.execute("SELECT id, sha256, ext FROM photos WHERE head_hash IS NULL").fetchall()
        for r in rows:
            try:
                c.execute("UPDATE photos SET head_hash=? WHERE id=?",
                          (imaging.head_hash(imaging.original_path(settings, r["sha256"], r["ext"])), r["id"]))
            except OSError:
                pass

    backfill_fingerprints()

    class DeleteAllBody(BaseModel):
        confirm: str  # debe ser "ELIMINAR": evita borrados accidentales desde cualquier cliente

    @app.post("/api/photos/delete-all")
    def delete_all(body: DeleteAllBody):
        """Quita TODAS las fotos de RaceFinder: copias, miniaturas, vistas previas, recortes, dorsales,
        caras y etiquetas de evaluación. No toca los archivos de origen del usuario ni los ajustes."""
        if body.confirm != "ELIMINAR":
            raise HTTPException(422, 'Escribe "ELIMINAR" para confirmar')
        was_paused = worker.is_paused()
        worker.cancel()  # que el análisis no siga con fotos que van a desaparecer
        try:
            for _ in range(100):  # espera a que termine la foto en curso (máx. ~10 s)
                if worker.current is None:
                    break
                time.sleep(0.1)
            c = db.conn()
            n = c.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
            c.execute("DELETE FROM photos")  # en cascada: dorsales, caras y etiquetas de evaluación
            for d in (settings.originals, settings.thumbs, settings.previews, settings.crops, settings.tmp):
                for sub in d.iterdir():
                    if sub.is_dir():
                        shutil.rmtree(sub, ignore_errors=True)
                    else:
                        sub.unlink(missing_ok=True)
            c.execute("VACUUM")
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # sin copias de los datos borrados en el diario
        finally:
            if not was_paused:
                worker.resume()
        return {"deleted": n}

    # ---------- importar una carpeta del disco (rápido: lo lee el servidor, no el navegador) ----------
    importer = ImportJob(db, settings, on_done=worker.kick)
    app.state.importer = importer

    def set_pref(key, value):
        db.conn().execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def get_pref(key):
        r = db.conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else ""

    @app.post("/api/system/pick-folder")
    def pick_folder(body: PickFolderBody):
        """Abre el selector de carpetas del sistema (RaceFinder corre en tu propio equipo). Devuelve la ruta o null."""
        code = ("import sys, tkinter as tk\nfrom tkinter import filedialog as fd\n"
                "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True); r.update()\n"
                "print(fd.askdirectory(title=sys.argv[1], initialdir=sys.argv[2] or None, parent=r) or '')")
        initial = get_pref("last_pick_dir")
        try:
            out = subprocess.run([sys.executable, "-c", code, body.title, initial if os.path.isdir(initial) else ""],
                                 capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.SubprocessError):
            raise HTTPException(501, "No se pudo abrir el selector de carpetas")
        if out.returncode != 0:
            raise HTTPException(501, "No se pudo abrir el selector de carpetas")
        path = out.stdout.strip().splitlines()[-1].strip() if out.stdout.strip() else ""
        if path:
            path = os.path.normpath(path)
            set_pref("last_pick_dir", path)
        return {"path": path or None}

    @app.post("/api/import/folder")
    def import_folder(body: ImportFolderBody):
        if shutil.disk_usage(settings.data_dir).free < MIN_FREE_BYTES:
            raise HTTPException(507, "Queda poco espacio en el disco. Libera espacio y vuelve a intentarlo.")
        try:
            importer.start(body.path)
        except ValueError as e:
            raise HTTPException(422, str(e))
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        return importer.status()

    @app.get("/api/import/status")
    def import_status():
        return importer.status()

    @app.post("/api/import/cancel")
    def import_cancel():
        importer.cancel()
        return importer.status()

    # ---------- procesamiento ----------
    @app.get("/api/settings")
    def get_settings():
        return load_settings()

    @app.put("/api/settings")
    def put_settings(body: SettingsBody):
        if body.mode not in MODES:
            raise HTTPException(422, "Modo inválido")
        if body.min_number > body.max_number:
            raise HTTPException(422, "El dorsal mínimo no puede ser mayor que el máximo")
        c = db.conn()
        if body.faces_enabled and not load_settings()["faces_enabled"] and not body.face_consent:
            raise HTTPException(422, "Para activar la búsqueda por cara hace falta el consentimiento explícito.")
        if body.faces_enabled and body.face_consent:
            c.execute("INSERT INTO settings(key,value) VALUES('faces_consent_at', datetime('now')) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        for k, v in body.model_dump(exclude={"face_consent"}).items():
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
        apply_mode(body.mode)
        worker.kick()  # si se acaba de activar el índice facial, empieza ya
        return load_settings()

    @app.post("/api/process")
    def process(reprocess_errors: bool = True, reanalyze: bool = False):
        c = db.conn()
        if reanalyze:
            c.execute("UPDATE photos SET ocr_status='pending', ocr_attempts=0")
        if reprocess_errors:
            c.execute("UPDATE photos SET ocr_status='pending', ocr_attempts=0 WHERE ocr_status='error'")
            c.execute("UPDATE photos SET face_status='pending', face_attempts=0 WHERE face_status='error'")
        worker.resume()
        return stats()

    @app.post("/api/process/cancel")
    def process_cancel():
        worker.cancel()
        return stats()

    @app.post("/api/photos/{pid}/reprocess")
    def reprocess(pid: int):
        get_photo(pid)
        db.conn().execute("UPDATE photos SET ocr_status='pending', ocr_attempts=0 WHERE id=?", (pid,))
        worker.resume()
        return {"queued": pid}

    # ---------- búsqueda ----------
    @app.get("/api/search")
    def search(bib: str, mode: str = "exact", min_conf: float = 0.0, limit: int = 1000):
        """match: exact (lectura fiable o confirmada) · doubtful (exacto con OCR < umbral) · similar (distancia 1)."""
        bib = bib.strip()
        if not BIB_RE.match(bib):
            raise HTTPException(422, "El dorsal debe tener entre 1 y 5 dígitos")
        c = db.conn()
        cfg = load_settings()
        rng = (cfg["min_number"], cfg["max_number"])
        # candidatos en SQL: mismo número o longitud ±1 (los similares se filtran después)
        if mode == "similar":
            rows = c.execute("SELECT * FROM bib_detections WHERE review!='rejected' AND confidence>=? "
                             "AND LENGTH(number) BETWEEN ? AND ? AND (review='manual' OR CAST(number AS INTEGER) BETWEEN ? AND ?)",
                             (min_conf, len(bib) - 1, len(bib) + 1, *rng)).fetchall()
        else:
            rows = c.execute("SELECT * FROM bib_detections WHERE review!='rejected' AND confidence>=? AND number=? "
                             "AND (review='manual' OR CAST(number AS INTEGER) BETWEEN ? AND ?)",
                             (min_conf, bib, *rng)).fetchall()
        rank = {"exact": 3, "doubtful": 2, "similar": 1}
        hits = {}
        for b in rows:
            if b["number"] == bib:
                trusted = b["review"] in ("confirmed", "manual") or b["confidence"] >= settings.doubtful_below
                kind = "exact" if trusted else "doubtful"
            elif mode == "similar" and similar_numbers(bib, b["number"]):
                kind = "similar"
            else:
                continue
            h = hits.setdefault(b["photo_id"], {"match": kind, "score": 0.0, "evidence": []})
            if rank[kind] > rank[h["match"]]:
                h["match"] = kind
            s_ = b["confidence"] + rank[kind] + (0.5 if b["review"] in ("confirmed", "manual") else 0)
            h["score"] = max(h["score"], s_)
            h["evidence"].append({"bib_id": b["id"], "number": b["number"], "confidence": b["confidence"],
                                  "bbox": json.loads(b["bbox"]), "review": b["review"], "kind": kind})
        ids = sorted(hits, key=lambda i: -hits[i]["score"])[:max(1, min(limit, 5000))]
        photos = {}
        if ids:
            q = ",".join("?" * len(ids))
            photos = {r["id"]: r for r in c.execute(f"SELECT * FROM photos WHERE id IN ({q})", ids)}
        return {"query": bib, "mode": mode, "count": len(ids),
                "results": [{**photo_row(photos[i]), "match": hits[i]["match"], "score": round(hits[i]["score"], 4),
                             "evidence": hits[i]["evidence"]} for i in ids]}

    # ---------- revisión manual ----------
    @app.post("/api/photos/{pid}/bibs")
    def add_bib(pid: int, body: ManualBib):
        get_photo(pid)
        n = body.number.strip()
        if not BIB_RE.match(n):
            raise HTTPException(422, "Dorsal inválido")
        cur = db.conn().execute(
            "INSERT INTO bib_detections(photo_id,number,raw_text,confidence,bbox,review) VALUES(?,?,?,?,?,'manual')",
            (pid, n, n, 1.0, "[0,0,0,0]"))
        return {"id": cur.lastrowid}

    @app.patch("/api/bibs/{bid}")
    def review_bib(bid: int, body: ReviewBody):
        if body.review not in ("confirmed", "rejected", "auto"):
            raise HTTPException(422, "Valor de revisión inválido")
        cur = db.conn().execute("UPDATE bib_detections SET review=? WHERE id=?", (body.review, bid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Detección no encontrada")
        return {"id": bid, "review": body.review}

    # ---------- exportación ----------
    def zip_response(ids):
        ids = list(dict.fromkeys(ids))[:20000]
        if not ids:
            raise HTTPException(422, "No hay fotos seleccionadas")
        q = ",".join("?" * len(ids))
        rows = db.conn().execute(f"SELECT * FROM photos WHERE id IN ({q})", ids).fetchall()
        if not rows:
            raise HTTPException(404, "Ninguna foto encontrada")

        class Sink:
            """Destino no posicionable: zipfile escribe con descriptores de datos y se emite en streaming."""
            def __init__(self):
                self.buf = bytearray()
            def write(self, b):
                self.buf += b
                return len(b)
            def flush(self):
                pass
            def take(self):
                out = bytes(self.buf)
                self.buf.clear()
                return out

        def gen():
            # ZIP_STORED: los originales se copian byte a byte, sin recomprimir ni pasar por disco.
            sink, used = Sink(), set()
            with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
                for r in rows:
                    name, i = r["original_name"], 1
                    while name.lower() in used:
                        stem, dot, ext = r["original_name"].rpartition(".")
                        name = f"{stem or r['original_name']}_{i}{dot}{ext}" if dot else f"{r['original_name']}_{i}"
                        i += 1
                    used.add(name.lower())
                    src = imaging.original_path(settings, r["sha256"], r["ext"])
                    with open(src, "rb") as f, z.open(zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0)), "w", force_zip64=True) as w:
                        while chunk := f.read(1024 * 1024):
                            w.write(chunk)
                            if len(sink.buf) >= 1024 * 1024:
                                yield sink.take()
                    yield sink.take()
            yield sink.take()

        fname = f"racefinder-{len(rows)}-fotos.zip"
        return StreamingResponse(gen(), media_type="application/zip",
                                 headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    @app.post("/api/export/save")
    def export_save(body: SaveBody):
        """Copia los originales a una carpeta de tu disco (sin ZIP ni descarga del navegador).
        No sobrescribe: si ya hay un archivo con ese nombre y distinto contenido, añade _1, _2…"""
        dest = Path(body.dest).expanduser()
        if not dest.is_absolute():
            raise HTTPException(422, "La carpeta de destino debe ser una ruta absoluta")
        sub = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", body.subfolder).strip(" .")
        if sub:
            dest = dest / sub
        ids = list(dict.fromkeys(body.ids))
        rows = []
        for k in range(0, len(ids), 500):
            chunk = ids[k:k + 500]
            rows += db.conn().execute(f"SELECT * FROM photos WHERE id IN ({','.join('?' * len(chunk))})", chunk).fetchall()
        if not rows:
            raise HTTPException(404, "Ninguna foto encontrada")
        try:
            dest.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(dest).free
        except OSError as e:
            raise HTTPException(422, f"No se puede usar esa carpeta ({type(e).__name__})")
        if free < sum(r["size"] for r in rows) + MIN_FREE_BYTES // 4:
            raise HTTPException(507, "No hay espacio suficiente en el destino para esas fotos")
        saved = skipped = 0
        failed = []
        for r in rows:
            src = imaging.original_path(settings, r["sha256"], r["ext"])
            stem, dot, ext = r["original_name"].rpartition(".")
            stem, ext = (stem, "." + ext) if dot else (r["original_name"], "")
            name, i = r["original_name"], 1
            try:
                while (dest / name).exists():
                    if (dest / name).stat().st_size == r["size"]:
                        name = None   # mismo nombre y tamaño: ya está guardada
                        break
                    name = f"{stem}_{i}{ext}"; i += 1
                if name is None:
                    skipped += 1
                    continue
                tmp = dest / f".{name}.{uuid.uuid4().hex[:8]}.part"
                try:
                    shutil.copyfile(src, tmp)
                    os.replace(tmp, dest / name)
                finally:
                    tmp.unlink(missing_ok=True)
                saved += 1
            except OSError as e:
                failed.append(f"{r['original_name']}: {type(e).__name__}")
                if e.errno == errno.ENOSPC:
                    break
        set_pref("last_pick_dir", str(dest.parent if sub else dest))
        if body.open_after and saved + skipped:
            try:
                if sys.platform == "win32":
                    os.startfile(str(dest))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(dest)])
                else:
                    subprocess.Popen(["xdg-open", str(dest)])
            except Exception:
                pass
        return {"saved": saved, "skipped": skipped, "failed": failed[:20], "dest": str(dest)}

    @app.post("/api/export")
    def export(body: ExportRequest):
        return zip_response(body.ids)

    @app.post("/api/export/download")
    def export_download(ids: str = Form(...)):
        """Igual que /api/export pero desde un formulario: el navegador guarda el ZIP en disco mientras llega."""
        try:
            parsed = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(422, "Lista de fotos inválida")
        return zip_response(parsed)

    # ---------- reconocimiento facial (opcional) ----------
    def require_faces():
        if not load_settings()["faces_enabled"]:
            raise HTTPException(409, "La búsqueda por cara está desactivada. Actívala en Ajustes.")

    def face_rows(where="", args=()):
        return db.conn().execute(f"SELECT id, photo_id, bbox, score, emb FROM faces {where}", args).fetchall()

    def marks(n):
        return ",".join("?" * n)

    @app.get("/api/faces/for-bib")
    def faces_for_bib(bib: str):
        """Caras de las fotos donde se ha leído el dorsal; 'preselect' indica las que probablemente son del corredor."""
        require_faces()
        bib = bib.strip()
        if not BIB_RE.match(bib):
            raise HTTPException(422, "Dorsal inválido")
        c = db.conn()
        ids, out = facemod.candidates_for_bib(c, bib, settings.doubtful_below)
        indexed = c.execute(f"SELECT COUNT(*) FROM photos WHERE face_status='done' AND id IN ({marks(len(ids)) or 'NULL'})", ids).fetchone()[0]
        return {"bib": bib, "photos": len(ids), "indexed": indexed,
                "faces": [{k: v for k, v in f.items() if k != "emb"} for f in out[:60]]}

    @app.post("/api/faces/search")
    def faces_search(body: FaceSearchBody, limit: int = 500):
        """Fotos con caras parecidas a las de referencia elegidas por el usuario. Puntuación = coseno, no probabilidad."""
        require_faces()
        best = facemod.search(db.conn(), body.face_ids)
        if not best and not face_rows(f"WHERE id IN ({marks(len(body.face_ids))})", body.face_ids):
            raise HTTPException(404, "No se encontraron esas caras")
        ids = sorted(best, key=lambda i: -best[i][0])[:max(1, min(limit, 5000))]
        photos, b = {}, {}
        if ids:
            photos = {r["id"]: r for r in db.conn().execute(f"SELECT * FROM photos WHERE id IN ({marks(len(ids))})", ids)}
            b = bibs_for(ids)
        res = []
        for i in ids:
            sim, r = best[i]
            res.append({**photo_row(photos[i], b[i]), "face": {
                "face_id": r["id"], "similarity": round(sim, 3), "bbox": json.loads(r["bbox"]),
                "strength": "alta" if sim >= facemod.STRONG_THRESHOLD else "media"}})
        return {"count": len(res), "threshold": facemod.MATCH_THRESHOLD, "results": res}

    @app.get("/api/faces/{fid}/crop")
    def face_crop(fid: int):
        require_faces()
        r = db.conn().execute("SELECT f.bbox, p.sha256, p.ext FROM faces f JOIN photos p ON p.id=f.photo_id WHERE f.id=?", (fid,)).fetchone()
        if not r:
            raise HTTPException(404, "Cara no encontrada")
        path = imaging.make_crop(settings, r["sha256"], r["ext"], json.loads(r["bbox"]), pad=(0.35, 0.35), size=(200, 200))
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})  # biométrico: sin caché del navegador

    @app.delete("/api/faces")
    def faces_delete_all():
        """Borra todos los datos faciales derivados (vectores y recortes) y desactiva la función."""
        c = db.conn()
        rows = c.execute("SELECT f.bbox, p.sha256 FROM faces f JOIN photos p ON p.id=f.photo_id").fetchall()
        c.execute("DELETE FROM faces")
        c.execute("UPDATE photos SET face_status='pending'")
        c.execute("INSERT INTO settings(key,value) VALUES('faces_enabled','False') ON CONFLICT(key) DO UPDATE SET value='False'")
        for r in rows:
            x0, y0, x1, y1 = json.loads(r["bbox"])
            (settings.crops / r["sha256"][:2] / f"{r['sha256']}_{x0}_{y0}_{x1}_{y1}.jpg").unlink(missing_ok=True)
        c.execute("DELETE FROM settings WHERE key='faces_consent_at'")
        c.execute("VACUUM")                          # reescribe el archivo sin las páginas liberadas
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # y vacía el diario WAL, que conservaría copias
        return {"deleted": len(rows)}

    # ---------- evaluación ----------
    @app.get("/api/eval/summary")
    def eval_summary():
        c = db.conn()
        out = {"tags": TAGS, "splits": {}, "unlabeled": c.execute(
            "SELECT COUNT(*) FROM photos WHERE id NOT IN (SELECT photo_id FROM gt_labels)").fetchone()[0]}
        for sp in ("tune", "test"):
            n = c.execute("SELECT COUNT(*), COALESCE(SUM(state='labeled'),0), COALESCE(SUM(state='no_bib'),0) "
                          "FROM gt_labels WHERE split=?", (sp,)).fetchone()
            runs = c.execute("SELECT COUNT(*) FROM eval_runs WHERE split=?", (sp,)).fetchone()[0]
            out["splits"][sp] = {"photos": n[0], "with_bibs": n[1], "no_bib": n[2], "runs": runs}
        out["status"] = evaluator.state
        return out

    @app.get("/api/eval/photos")
    def eval_photos(state: str = "unlabeled", limit: int = 60, offset: int = 0):
        limit = max(1, min(limit, 500))
        where = {"unlabeled": "g.photo_id IS NULL", "labeled": "g.photo_id IS NOT NULL", "all": "1=1"}.get(state)
        if where is None:
            raise HTTPException(422, "state inválido")
        q = f"FROM photos p LEFT JOIN gt_labels g ON g.photo_id=p.id WHERE {where}"
        total = db.conn().execute(f"SELECT COUNT(*) {q}").fetchone()[0]
        rows = db.conn().execute(f"SELECT p.*, g.state AS g_state, g.bibs AS g_bibs, g.present AS g_present, g.tags AS g_tags, g.split AS g_split "
                                 f"{q} ORDER BY p.id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return {"total": total, "photos": [{**photo_row(r), "label": None if r["g_state"] is None else {
            "state": r["g_state"], "bibs": json.loads(r["g_bibs"]), "present": json.loads(r["g_present"]), "tags": json.loads(r["g_tags"]), "split": r["g_split"]}}
            for r in rows]}

    @app.put("/api/eval/labels/{pid}")
    def eval_put_label(pid: int, body: LabelBody):
        r = get_photo(pid)
        if body.state not in ("labeled", "no_bib"):
            raise HTTPException(422, "state inválido")
        bibs = sorted(set(body.bibs)) if body.state == "labeled" else []
        if any(not BIB_RE.match(b) for b in bibs) or (body.state == "labeled" and not bibs):
            raise HTTPException(422, "Indica al menos un dorsal válido (1-5 dígitos) o marca 'sin dorsal legible'")
        if any(t not in TAGS for t in body.tags):
            raise HTTPException(422, "Etiqueta desconocida")
        present = sorted(set(body.present) - set(bibs))
        if any(not BIB_RE.match(b) for b in present):
            raise HTTPException(422, "Dorsal inválido en 'aparece sin dorsal legible'")
        sp = split_for(r["sha256"])
        db.conn().execute(
            "INSERT INTO gt_labels(photo_id,state,bibs,present,tags,split) VALUES(?,?,?,?,?,?) ON CONFLICT(photo_id) DO UPDATE SET "
            "state=excluded.state,bibs=excluded.bibs,present=excluded.present,tags=excluded.tags,updated_at=datetime('now')",
            (pid, body.state, json.dumps(bibs), json.dumps(present), json.dumps(sorted(set(body.tags))), sp))
        return {"photo_id": pid, "split": sp}

    @app.delete("/api/eval/labels/{pid}")
    def eval_del_label(pid: int):
        db.conn().execute("DELETE FROM gt_labels WHERE photo_id=?", (pid,))
        return {"deleted": pid}

    @app.post("/api/eval/run")
    def eval_run(body: EvalRunBody):
        if body.split not in ("tune", "test"):
            raise HTTPException(422, "split inválido")
        c = db.conn()
        if c.execute("SELECT COUNT(*) FROM gt_labels WHERE split=?", (body.split,)).fetchone()[0] == 0:
            raise HTTPException(409, "No hay fotos etiquetadas en esa partición")
        prev = c.execute("SELECT COUNT(*) FROM eval_runs WHERE split='test'").fetchone()[0]
        if body.split == "test" and not body.confirm_test:
            raise HTTPException(409, f"'test' es la validación final y ya se ejecutó {prev} vez/veces. "
                                     "Confirma que no has ajustado parámetros con estas fotos.")
        s = stats()["ocr"]
        if s.get("pending", 0) + s.get("processing", 0) > 0:
            raise HTTPException(409, "Espera a que termine el análisis normal antes de evaluar (para medir tiempos limpios).")
        try:
            evaluator.start(body.split, body.params)
        except ValueError as e:
            raise HTTPException(422, str(e))
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        return evaluator.state

    @app.post("/api/eval/search-run")
    def eval_search_run(body: EvalRunBody):
        """Mide la búsqueda tal como la ve el usuario (dorsal, cara y combinada) con las lecturas ya guardadas."""
        if body.split not in ("tune", "test"):
            raise HTTPException(422, "split inválido")
        c = db.conn()
        if c.execute("SELECT COUNT(*) FROM gt_labels WHERE split=?", (body.split,)).fetchone()[0] == 0:
            raise HTTPException(409, "No hay fotos etiquetadas en esa partición")
        if body.split == "test" and not body.confirm_test:
            raise HTTPException(409, "'test' es la validación final. Confirma que no has ajustado parámetros con estas fotos.")
        st = stats()
        if st["ocr"].get("pending", 0) + st["ocr"].get("processing", 0) > 0:
            raise HTTPException(409, "Espera a que terminen de leerse los dorsales.")
        faces_ok = st["faces"]["enabled"] and st["faces"]["status"].get("pending", 0) + st["faces"]["status"].get("processing", 0) == 0
        if st["faces"]["enabled"] and not faces_ok:
            raise HTTPException(409, "Espera a que termine el análisis de caras.")
        m = evaluate_search(c, body.split, settings.doubtful_below, faces_ok)
        params = {"kind": "search", "face_threshold": facemod.MATCH_THRESHOLD, "doubtful_below": settings.doubtful_below,
                  "faces": faces_ok}
        cur = c.execute("INSERT INTO eval_runs(split,params,n_photos,metrics,details) VALUES(?,?,?,?,?)",
                        (body.split, json.dumps(params), m["photos"], json.dumps(m), "[]"))
        return {"run_id": cur.lastrowid, "metrics": m}

    @app.get("/api/eval/status")
    def eval_status():
        return evaluator.state

    @app.get("/api/eval/runs")
    def eval_runs():
        rows = db.conn().execute("SELECT * FROM eval_runs ORDER BY id DESC LIMIT 50").fetchall()
        return {"runs": [{"id": r["id"], "created_at": r["created_at"], "split": r["split"], "n_photos": r["n_photos"],
                          "params": json.loads(r["params"]), "metrics": json.loads(r["metrics"])} for r in rows]}

    if settings.serve_ui and settings.frontend_dist.exists():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return app


def get_app():
    return create_app()
