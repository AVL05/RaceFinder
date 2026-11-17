import sqlite3
import threading

from .evaluation import EVAL_SCHEMA

SCHEMA = """
CREATE TABLE IF NOT EXISTS photos(
  id INTEGER PRIMARY KEY,
  sha256 TEXT NOT NULL UNIQUE,
  original_name TEXT NOT NULL,
  ext TEXT NOT NULL,
  size INTEGER NOT NULL,
  width INTEGER, height INTEGER,
  added_at TEXT NOT NULL DEFAULT (datetime('now')),
  ocr_status TEXT NOT NULL DEFAULT 'pending',   -- pending|processing|done|error
  ocr_error TEXT,
  ocr_engine TEXT
);
CREATE TABLE IF NOT EXISTS bib_detections(
  id INTEGER PRIMARY KEY,
  photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
  number TEXT NOT NULL,
  raw_text TEXT NOT NULL,
  confidence REAL NOT NULL,          -- puntuación del OCR, NO probabilidad calibrada
  bbox TEXT NOT NULL,                -- JSON [x0,y0,x1,y1] en píxeles de la imagen original
  review TEXT NOT NULL DEFAULT 'auto'  -- auto|confirmed|rejected|manual
);
CREATE INDEX IF NOT EXISTS idx_bib_number ON bib_detections(number);
CREATE INDEX IF NOT EXISTS idx_bib_photo ON bib_detections(photo_id);
CREATE INDEX IF NOT EXISTS idx_photo_status ON photos(ocr_status);
CREATE TABLE IF NOT EXISTS faces(
  id INTEGER PRIMARY KEY,
  photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
  bbox TEXT NOT NULL,                -- JSON [x0,y0,x1,y1] en px de la imagen tal como se ve
  score REAL NOT NULL,               -- confianza del detector
  emb BLOB NOT NULL                  -- vector anónimo float32[128]; sin nombres ni identidades
);
CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_id);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',  -- queued|running|cancelled|done
  total INTEGER NOT NULL DEFAULT 0,
  done INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Database:
    """Una conexión por hilo, WAL, claves foráneas activas."""

    def __init__(self, path):
        self.path = str(path)
        self._local = threading.local()
        with self.conn() as c:
            c.executescript(SCHEMA)
            c.executescript(EVAL_SCHEMA)
            if "present" not in {r[1] for r in c.execute("PRAGMA table_info(gt_labels)")}:
                c.execute("ALTER TABLE gt_labels ADD COLUMN present TEXT NOT NULL DEFAULT '[]'")
            cols = {r[1] for r in c.execute("PRAGMA table_info(photos)")}
            if "face_status" not in cols:  # migración: índice facial opcional
                c.execute("ALTER TABLE photos ADD COLUMN face_status TEXT NOT NULL DEFAULT 'pending'")
            if "head_hash" not in cols:  # migración: huella rápida para reanudar importaciones sin reenviar
                c.execute("ALTER TABLE photos ADD COLUMN head_hash TEXT")
            c.execute("CREATE INDEX IF NOT EXISTS idx_photo_fingerprint ON photos(size, head_hash)")
            if "ocr_attempts" not in cols:  # migración: reintentos automáticos ante fallos puntuales
                c.execute("ALTER TABLE photos ADD COLUMN ocr_attempts INTEGER NOT NULL DEFAULT 0")
            if "face_attempts" not in cols:
                c.execute("ALTER TABLE photos ADD COLUMN face_attempts INTEGER NOT NULL DEFAULT 0")
            # la cola elige "la siguiente pendiente": con decenas de miles de fotos necesita índice propio
            c.execute("CREATE INDEX IF NOT EXISTS idx_photo_ocr_queue ON photos(ocr_status, ocr_attempts, id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_photo_face_queue ON photos(face_status, face_attempts, id)")

    def conn(self):
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA synchronous=NORMAL")   # seguro en WAL; evita un fsync por cada INSERT de la importación
            c.execute("PRAGMA busy_timeout=30000")
            self._local.c = c
        return c
