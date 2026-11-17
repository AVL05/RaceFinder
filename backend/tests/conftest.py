import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app.bibs import BibReader
from app.config import Settings
from app.main import create_app


def make_image(texts=(), size=(1600, 1000), fmt="JPEG", seed=0):
    """Imagen sintética: fondo + rectángulos blancos con números. Solo para pruebas de
    fontanería; NO mide precisión sobre fotos reales de carreras."""
    im = Image.new("RGB", size, (60 + seed % 50, 110, 80))
    d = ImageDraw.Draw(im)
    for k in range(5):  # marca única por semilla (evita que JPEG deje imágenes idénticas)
        d.rectangle((20 + k * 60, 20, 70 + k * 60, 70), fill=(255 if seed >> k & 1 else 0, 0, 0))
    font = ImageFont.truetype("arialbd.ttf", 140)
    x = 120
    for t in texts:
        d.rectangle((x, 300, x + 120 + 110 * len(t), 520), fill=(250, 250, 250))
        d.text((x + 30, 330), t, fill=(0, 0, 0), font=font)
        x += 200 + 110 * len(t)
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


@pytest.fixture
def settings(tmp_path):
    s = Settings(data_dir=tmp_path / "data")
    s.allowed_hosts = s.allowed_hosts + ["testserver"]  # TestClient usa este host
    return s


@pytest.fixture
def client(settings):
    app = create_app(settings, start_worker=False)
    with TestClient(app) as c:
        c.app_ = app
        yield c


@pytest.fixture(scope="session")
def real_reader():
    return BibReader()


@pytest.fixture
def real_client(settings, real_reader):
    app = create_app(settings, reader=real_reader, start_worker=True)
    with TestClient(app) as c:
        yield c


def wait_done(client, timeout=120):
    t = time.time()
    while time.time() - t < timeout:
        s = client.get("/api/stats").json()
        if s["ocr"].get("pending", 0) == 0 and s["ocr"].get("processing", 0) == 0:
            return s
        time.sleep(0.3)
    raise AssertionError("timeout esperando OCR")
