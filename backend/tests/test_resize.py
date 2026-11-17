"""Redimensionado rápido opcional: apagado por defecto (comportamiento de siempre) y casi idéntico al encenderlo."""
import io

import cv2
import numpy as np
import pytest
from PIL import Image

from app import resize
from app.bibs import BibReader
from tests.conftest import make_image


@pytest.fixture(autouse=True)
def reset():
    resize.set_fast(None)
    yield
    resize.set_fast(None)


def natural(w=1800, h=1200):
    return Image.fromarray(cv2.resize(cv2.imread("../frontend/e2e/.fixtures/cache/messi.jpg"), (w, h))[:, :, ::-1].copy())


def test_off_by_default_and_identical_to_pil_lanczos(monkeypatch):
    monkeypatch.delenv("RACEFINDER_FAST_RESIZE", raising=False)
    im = natural()
    assert not resize.fast_enabled()
    assert np.array_equal(resize.resize_rgb(im, (900, 600)), np.asarray(im.resize((900, 600), Image.LANCZOS)))


@pytest.mark.parametrize("v,expected", [("1", True), ("true", True), ("Sí", True), ("0", False), ("", False), ("no", False)])
def test_env_switch(monkeypatch, v, expected):
    monkeypatch.setenv("RACEFINDER_FAST_RESIZE", v)
    assert resize.fast_enabled() is expected


def test_fast_is_close_to_lanczos():
    im = natural()
    legacy = resize.resize_rgb(im, (900, 600))
    resize.set_fast(True)
    fast = resize.resize_rgb(im, (900, 600))
    assert fast.shape == legacy.shape == (600, 900, 3) and fast.dtype == np.uint8
    assert np.abs(fast.astype(int) - legacy.astype(int)).mean() < 1.0


def test_bib_reading_same_with_fast_resize(tmp_path):
    """Con dorsales sintéticos grandes (fuerza reducción y mosaico) se leen los mismos números con y sin él."""
    p = tmp_path / "a.jpg"
    p.write_bytes(make_image(["123", "4567"], size=(4200, 2800), seed=3))
    reader = BibReader(device="cpu")
    legacy = {d.number for d in reader.read(p)}
    resize.set_fast(True)
    fast = {d.number for d in reader.read(p)}
    assert legacy == fast
