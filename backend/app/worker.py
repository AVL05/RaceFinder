"""Cola local persistente: el estado vive en SQLite, el hilo solo consume.
Al reiniciar, lo 'processing' vuelve a 'pending' (reanudación).

Robustez (miles de fotos, horas de trabajo):
 - el hilo nunca muere: cualquier excepción se registra, se espera un poco y se sigue;
 - un fallo puntual de una foto se reintenta (MAX_ATTEMPTS); las que fallan van al final de la cola;
 - lo que quede en 'processing' sin que nadie lo trabaje se devuelve a 'pending'.
"""
import json
import os
import threading
import traceback

from .bibs import BibReader
from .db import write_transaction
from .faces import FaceEngine, ensure_models, models_ready, to_blob
from .hardware import MAX_WORKERS, auto_workers, lower_priority
from .imaging import original_path, make_preview

MAX_ATTEMPTS = 3
# Varias fotos a la vez: decodificar y preparar la imagen es de un solo hilo y deja la CPU ociosa mientras ONNX
# o la GPU esperan. El número se ajusta solo a la máquina (núcleos, RAM y GPU: ver hardware.auto_workers);
# se puede forzar con RACEFINDER_WORKERS (máx. 16).


class Worker:
    def __init__(self, db, settings, reader=None, faces_enabled=lambda: False, face_engine=None, n_workers=None):
        self.db, self.settings = db, settings
        self.reader = reader or BibReader()
        self.faces_enabled = faces_enabled
        self.face_engine = face_engine or FaceEngine()
        self.face_error = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._paused = threading.Event()
        forced = n_workers or os.environ.get("RACEFINDER_WORKERS")
        try:
            forced = int(forced) if forced else None
        except ValueError:
            forced = None
        self.workers_auto = not forced
        self.n_workers = max(1, min(MAX_WORKERS, forced or auto_workers(getattr(self.reader, "device", "cpu"))))
        self.threads = []
        self._lock = threading.Lock()    # reclamar una foto y registrarla como activa es una sola operación
        self._active = set()
        self._face_engines = {}
        self.last_error = None

    @property
    def current(self):
        """Id de una foto en curso (o None si no hay ninguna): lo usa el borrado total para esperar."""
        with self._lock:
            return min((i for _, i in self._active), default=None)

    @property
    def thread(self):
        return self.threads[0] if self.threads else None

    def start(self):
        lower_priority()
        c = self.db.conn()
        c.execute("UPDATE photos SET ocr_status='pending' WHERE ocr_status='processing'")
        c.execute("UPDATE photos SET face_status='pending' WHERE face_status='processing'")
        self.threads = []
        for i in range(self.n_workers):
            self._spawn(i)
        self._wake.set()

    def _spawn(self, i):
        t = threading.Thread(target=self._loop, args=(i,), daemon=True, name=f"ocr-worker-{i}")
        if i < len(self.threads):
            self.threads[i] = t
        else:
            self.threads.append(t)
        t.start()

    def alive(self) -> bool:
        return bool(self.threads) and all(t.is_alive() for t in self.threads)

    def _ensure_alive(self):
        """Red de seguridad: si algún hilo hubiera caído por algo imprevisto, se vuelve a lanzar."""
        if self._stop.is_set():
            return
        for i, t in enumerate(list(self.threads)):
            if not t.is_alive():
                self._spawn(i)

    def stop(self):
        self._stop.set()
        self._wake.set()
        for t in self.threads:
            t.join(timeout=3)

    def _engine(self, i):
        """Un motor facial por hilo (el detector guarda el tamaño de entrada: no se comparte entre hilos)."""
        if i == 0:
            return self.face_engine
        if i not in self._face_engines:
            self._face_engines[i] = FaceEngine(self.face_engine.models_dir)
        return self._face_engines[i]

    def _claim(self, kind):
        """Toma atómicamente la siguiente foto pendiente (varios hilos nunca cogen la misma)."""
        col = "ocr" if kind == "ocr" else "face"
        with self._lock:
            active_ids = tuple(pid for active_kind, pid in self._active if active_kind == kind)
            claimed = f"AND id NOT IN ({','.join('?' * len(active_ids))})" if active_ids else ""
            rows = self.db.conn().execute(
                f"UPDATE photos SET {col}_status='processing' WHERE id=(SELECT id FROM photos WHERE {col}_status='pending' "
                f"{claimed} ORDER BY {col}_attempts, id LIMIT 1) RETURNING id, sha256, ext, {col}_attempts AS attempts",
                active_ids,
            ).fetchall()
            if not rows:
                return None
            self._active.add((kind, rows[0]["id"]))
            return rows[0]

    def _done(self, kind, pid):
        with self._lock:
            self._active.discard((kind, pid))

    def kick(self):
        """Despierta al hilo. No anula una cancelación del usuario (ver resume)."""
        self._ensure_alive()
        self._wake.set()

    def resume(self):
        self._paused.clear()
        self.kick()

    def cancel(self):
        """Cancelación segura: termina la foto en curso y no toma más. Lo pendiente se conserva."""
        self._paused.set()

    def is_paused(self):
        return self._paused.is_set()

    def _loop(self, i=0):
        backoff = 1.0
        while not self._stop.is_set():
            self._wake.wait(timeout=2)
            self._wake.clear()
            while not self._stop.is_set() and not self._paused.is_set():
                try:
                    # primero los dorsales (lo que el usuario busca antes); después, si está activado, las caras
                    progressed = self._process_one() or (self.faces_enabled() and self._process_face(i))
                    backoff = 1.0
                except Exception as e:  # BD ocupada, disco, lo que sea: el análisis no se detiene
                    self.last_error = f"{type(e).__name__}: {e}"[:300]
                    traceback.print_exc()
                    self._release_stuck()
                    if self._stop.wait(backoff):
                        return
                    backoff = min(backoff * 2, 30.0)
                    continue
                if not progressed:
                    break
            self._release_stuck()

    def _release_stuck(self):
        """Fotos 'processing' que ningún hilo está trabajando (fallo al guardar el resultado): a la cola otra vez."""
        try:
            with self._lock:
                if self._active:  # otro hilo está trabajando: lo 'processing' es suyo
                    return
                c = self.db.conn()
                c.execute("UPDATE photos SET ocr_status='pending' WHERE ocr_status='processing'")
                c.execute("UPDATE photos SET face_status='pending' WHERE face_status='processing'")
        except Exception:
            traceback.print_exc()

    @staticmethod
    def _still_processing(conn, row, kind):
        # SQLite can reuse the id of a deleted photo. The hash and the
        # processing state identify the work that may still be published.
        return conn.execute(
            f"SELECT 1 FROM photos WHERE id=? AND sha256=? AND {kind}_status='processing'",
            (row["id"], row["sha256"]),
        ).fetchone() is not None

    def _process_one(self) -> bool:
        c = self.db.conn()
        # las que ya han fallado alguna vez van detrás de las nuevas: una foto rota no frena el resto
        row = self._claim("ocr")
        if not row:
            return False
        try:
            reader = self.reader
            dets = reader.read(original_path(self.settings, row["sha256"], row["ext"]))
            with write_transaction(c):
                if not self._still_processing(c, row, "ocr"):
                    return True
                # conserva revisiones manuales; reemplaza solo lo automático
                c.execute("DELETE FROM bib_detections WHERE photo_id=? AND review='auto'", (row["id"],))
                for d in dets:
                    c.execute("INSERT INTO bib_detections(photo_id,number,raw_text,confidence,bbox) VALUES(?,?,?,?,?)",
                              (row["id"], d.number, d.raw_text, d.confidence, json.dumps(d.bbox)))
                c.execute("UPDATE photos SET ocr_status='done', ocr_error=NULL, ocr_engine=?, ocr_attempts=0 WHERE id=?",
                          (reader.engine_name, row["id"]))
            try:  # el visor abre al instante: la vista previa queda lista tras el análisis
                make_preview(self.settings, row["sha256"], row["ext"])
            except Exception:
                pass
        except Exception as e:
            attempts = row["attempts"] + 1
            final = attempts >= MAX_ATTEMPTS or isinstance(e, FileNotFoundError)
            updated = c.execute("UPDATE photos SET ocr_status=?, ocr_attempts=?, ocr_error=? "
                                "WHERE id=? AND sha256=? AND ocr_status='processing'",
                                ("error" if final else "pending", attempts, f"{type(e).__name__}: {e}"[:300], row["id"], row["sha256"]))
            if updated.rowcount:
                traceback.print_exc()
        finally:
            self._done("ocr", row["id"])
        return True

    def _process_face(self, i=0) -> bool:
        c = self.db.conn()
        if not c.execute("SELECT 1 FROM photos WHERE face_status='pending' LIMIT 1").fetchone():
            return False
        if not models_ready(self.face_engine.models_dir):
            try:
                self.face_error = "Descargando los modelos faciales (38 MB, solo la primera vez)…"
                ensure_models(self.face_engine.models_dir)
                self.face_error = None
            except Exception:
                traceback.print_exc()
                self.face_error = "No se pudieron descargar los modelos faciales. Comprueba la conexión; se reintentará."
                self._stop.wait(30)
                return False
        row = self._claim("face")
        if not row:
            return False
        try:
            found = self._engine(i).index(original_path(self.settings, row["sha256"], row["ext"]))
            self.face_error = None
            with write_transaction(c):
                if not self._still_processing(c, row, "face"):
                    return True
                if not self.faces_enabled():
                    c.execute("UPDATE photos SET face_status='pending' WHERE id=?", (row["id"],))
                    return True
                c.execute("DELETE FROM faces WHERE photo_id=?", (row["id"],))
                for bbox, score, emb in found:
                    c.execute("INSERT INTO faces(photo_id,bbox,score,emb) VALUES(?,?,?,?)",
                              (row["id"], json.dumps(bbox), score, to_blob(emb)))
                c.execute("UPDATE photos SET face_status='done', face_attempts=0 WHERE id=?", (row["id"],))
        except Exception as e:
            attempts = row["attempts"] + 1
            final = attempts >= MAX_ATTEMPTS or isinstance(e, FileNotFoundError)
            updated = c.execute("UPDATE photos SET face_status=?, face_attempts=? WHERE id=? AND sha256=? AND face_status='processing'",
                                ("error" if final else "pending", attempts, row["id"], row["sha256"]))
            if updated.rowcount:
                traceback.print_exc()
        finally:
            self._done("face", row["id"])
        return True
