"""Reanudar importaciones: el navegador pregunta qué fotos ya están (tamaño + SHA-256 de los primeros 64 KB)."""
import hashlib
import io

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_image


def fp(data: bytes):
    return {"size": len(data), "head": hashlib.sha256(data[:64 * 1024]).hexdigest()}


def test_known_matches_browser_fingerprint(client):
    big = make_image(["184"], size=(3000, 2000), seed=90)        # > 64 KB: la huella usa solo el principio
    small = make_image(seed=91)
    assert len(big) > 64 * 1024
    client.post("/api/photos", files=[("files", ("a.jpg", io.BytesIO(big), "image/jpeg"))])
    new = make_image(seed=92)
    r = client.post("/api/photos/known", json={"items": [fp(big), fp(small), fp(new)]}).json()
    assert r["known"] == [True, False, False]
    # mismo principio pero distinto tamaño: no se confunde
    assert client.post("/api/photos/known", json={"items": [{**fp(big), "size": len(big) + 1}]}).json()["known"] == [False]
    assert client.post("/api/photos/known", json={"items": [{"size": 1, "head": "x"}]}).status_code == 422


def test_existing_libraries_are_backfilled(settings):
    app = create_app(settings, start_worker=False)
    with TestClient(app) as c:
        data = make_image(seed=93)
        c.post("/api/photos", files=[("files", ("b.jpg", io.BytesIO(data), "image/jpeg"))])
        app.state.db.conn().execute("UPDATE photos SET head_hash=NULL")   # biblioteca de antes de esta versión
    app2 = create_app(settings, start_worker=False)                       # al arrancar se rellena
    with TestClient(app2) as c2:
        assert c2.post("/api/photos/known", json={"items": [fp(data)]}).json()["known"] == [True]
