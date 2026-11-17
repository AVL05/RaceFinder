"""Configuración. Todo sobrescribible con variables de entorno RACEFINDER_*."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _int(name, default):
    return int(os.environ.get(name, default))


class Settings:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir or os.environ.get("RACEFINDER_DATA", ROOT / "data")).resolve()
        self.originals = self.data_dir / "originals"
        self.thumbs = self.data_dir / "thumbs"
        self.tmp = self.data_dir / "tmp"
        self.previews = self.data_dir / "previews"
        self.crops = self.data_dir / "crops"
        self.db_path = self.data_dir / "racefinder.sqlite3"
        self.max_file_bytes = _int("RACEFINDER_MAX_FILE_MB", 60) * 1024 * 1024
        self.max_pixels = _int("RACEFINDER_MAX_MEGAPIXELS", 100) * 1_000_000
        self.thumb_size = 480
        self.preview_size = 1600
        self.doubtful_below = float(os.environ.get("RACEFINDER_DOUBTFUL_BELOW", 0.85))
        self.allowed_ext = {".jpg", ".jpeg", ".png", ".webp"}
        self.allowed_formats = {"JPEG", "PNG", "WEBP"}
        self.cors_origins = [
            o for o in os.environ.get(
                "RACEFINDER_CORS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"
            ).split(",") if o
        ]
        self.allowed_hosts = ["localhost", "127.0.0.1", "[::1]"]
        self.frontend_dist = ROOT / "frontend" / "dist"
        # en desarrollo (pnpm run dev) la interfaz la sirve Vite; FastAPI solo da la API
        self.serve_ui = os.environ.get("RACEFINDER_DEV", "0") != "1"

    def ensure(self):
        for d in (self.originals, self.thumbs, self.previews, self.crops, self.tmp):
            d.mkdir(parents=True, exist_ok=True)
