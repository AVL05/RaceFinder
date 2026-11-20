"""Importación de una carpeta del disco, directamente desde el servidor.

Como RaceFinder se ejecuta en local, no hace falta que el navegador lea y suba cada foto por HTTP:
el servidor lee la carpeta él mismo, con varios hilos, y deja cada original como enlace duro (sin copiar
ni ocupar espacio extra) o, si el disco no lo permite, como copia. Las fotos que ya estaban se descartan
sin leerlas enteras (tamaño + huella de los primeros 64 KB).
Corre como tarea en segundo plano: sobrevive a recargar la página y se puede cancelar.
"""
import errno
import os
import shutil
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import imaging
from .catalog import album_clause, attach_photo, register_photo

MIN_FREE_BYTES = 2 * 1024 ** 3
MAX_ERRORS = 200


def scan(root: Path, allowed_ext, stop=lambda: False):
    """Todas las imágenes de la carpeta (y subcarpetas), sin seguir enlaces simbólicos."""
    out = []
    stack = [root]
    while stack and not stop():
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if not e.name.startswith("."):
                                stack.append(Path(e.path))
                        elif e.is_file() and Path(e.name).suffix.lower() in allowed_ext:
                            out.append(Path(e.path))
                    except OSError:
                        continue
        except OSError:
            continue
    out.sort()
    return out


class ImportJob:
    def __init__(self, db, settings, on_done=lambda: None, threads=None):
        self.db, self.settings, self.on_done = db, settings, on_done
        self.threads = max(1, min(16, int(threads or os.environ.get("RACEFINDER_IMPORT_THREADS", min(6, os.cpu_count() or 2)))))
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread = None
        self._state = self._blank()

    @staticmethod
    def _blank():
        return {"running": False, "phase": "idle", "path": None, "album": None, "total": 0, "done": 0, "added": 0, "duplicate": 0,
                "rejected": 0, "linked": 0, "copied": 0, "errors": [], "cancelled": False, "fatal": None}

    def status(self):
        with self._lock:
            s = dict(self._state)
            s["errors"] = list(s["errors"])
            return s

    def cancel(self):
        self._cancel.set()

    def start(self, path, album=None):
        root = Path(path).expanduser()
        if not root.is_absolute():
            raise ValueError("La ruta debe ser absoluta")
        if not root.is_dir():
            raise ValueError("Esa carpeta no existe")
        with self._lock:
            if self._state["running"]:
                raise RuntimeError("Ya hay una importación en curso")
            self._cancel.clear()
            self._state = {**self._blank(), "running": True, "phase": "scanning", "path": str(root), "album": album}
        self._thread = threading.Thread(target=self._run, args=(root, album), daemon=True, name="importer")
        self._thread.start()

    # -- interno --
    def _bump(self, **inc):
        with self._lock:
            for k, v in inc.items():
                self._state[k] += v

    def _err(self, msg):
        with self._lock:
            if len(self._state["errors"]) < MAX_ERRORS:
                self._state["errors"].append(msg)

    def _run(self, root, album):
        try:
            files = scan(root, self.settings.allowed_ext, self._cancel.is_set)
            with self._lock:
                self._state.update(total=len(files), phase="importing")
            with ThreadPoolExecutor(self.threads, thread_name_prefix="import") as ex:
                for _ in ex.map(lambda path: self._one(path, album), files):
                    pass
        except Exception as e:  # nunca deja la tarea 'running' para siempre
            traceback.print_exc()
            with self._lock:
                self._state["fatal"] = f"{type(e).__name__}: {e}"[:300]
        finally:
            with self._lock:
                self._state.update(running=False, phase="done", cancelled=self._cancel.is_set())
            try:
                self.on_done()
            except Exception:
                traceback.print_exc()

    def _one(self, path: Path, album=None):
        if self._cancel.is_set():
            return
        s, c = self.settings, self.db.conn()
        name = imaging.safe_name(path.name)
        created = None
        meta = None
        try:
            try:
                size = path.stat().st_size
                # ya importada (mismo tamaño y mismos primeros 64 KB): no se lee entera
                scope, args = album_clause(album, "id")
                if c.execute(f"SELECT 1 FROM photos WHERE size=? AND head_hash=? AND {scope}",
                             (size, imaging.head_hash(path), *args)).fetchone():
                    self._bump(duplicate=1)
                    return
                meta = imaging.ingest_path(s, path)
            except imaging.InvalidImage as e:
                self._bump(rejected=1); self._err(f"{name}: {e}")
                return
            except OSError as e:
                self._bump(rejected=1); self._err(f"{name}: no se pudo leer ({type(e).__name__})")
                return
            existing = c.execute("SELECT id FROM photos WHERE sha256=?", (meta["sha256"],)).fetchone()
            if existing:
                attach_photo(c, album, existing["id"])
                self._bump(duplicate=1)
                return
            if shutil.disk_usage(s.data_dir).free < MIN_FREE_BYTES:
                raise OSError(errno.ENOSPC, "disco lleno")
            created = imaging.commit_from_path(s, meta)
            imaging.make_thumb(s, meta["sha256"], meta["ext"])
            _, added = register_photo(c, meta, name, album)
            self._bump(**({"added": 1} if added else {"duplicate": 1}), **({created: 1} if created else {}))
        except Exception as e:
            if meta and created:            # sin fila en la BD nadie la borraría: no se dejan huérfanos
                imaging.original_path(s, meta["sha256"], meta["ext"]).unlink(missing_ok=True)
                imaging.thumb_path(s, meta["sha256"]).unlink(missing_ok=True)
            if isinstance(e, OSError) and e.errno == errno.ENOSPC:
                self._cancel.set()
                with self._lock:
                    self._state["fatal"] = "El disco se ha llenado. Libera espacio y vuelve a importar la carpeta: las fotos ya importadas se omitirán."
            self._bump(rejected=1); self._err(f"{name}: {type(e).__name__}")
        finally:
            self._bump(done=1)
