import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main as mainmod
from app.bibs import Detection
from app.main import create_app
from .conftest import make_image, wait_done


class FlakyReader:
    """Falla en la primera lectura de cada foto y, para una, siempre."""
    engine_name = "flaky"

    def __init__(self):
        self.calls = {}
        self.lock = threading.Lock()

    def with_config(self, cfg):
        return self

    def read(self, path):
        with self.lock:
            n = self.calls[path.name] = self.calls.get(path.name, 0) + 1
        if self.always_fail == path.name or n == 1:
            raise MemoryError("simulado")
        return [Detection("123", "123", 0.95, [1, 1, 50, 50])]

    always_fail = None


def upload(c, blobs):
    return c.post("/api/photos", files=[("files", (f"f{i}.jpg", b, "image/jpeg")) for i, b in enumerate(blobs)]).json()["results"]


def test_failed_photos_are_retried_then_marked_error(settings):
    reader = FlakyReader()
    app = create_app(settings, reader=reader, start_worker=True)
    with TestClient(app) as c:
        res = upload(c, [make_image(seed=i) for i in range(4)])
        # la última falla siempre
        sha_last = c.get("/api/photos?limit=1").json()["photos"][0]["v"]
        wait_done(c)
        # la primera lectura falló en todas, pero se reintentó: todas 'done' salvo la rota
        s = c.get("/api/stats").json()
        assert s["ocr"].get("done") == 4 and "error" not in s["ocr"]
        assert s["worker_alive"] is True


def test_always_failing_photo_ends_in_error_without_blocking_others(settings):
    reader = FlakyReader()
    app = create_app(settings, reader=reader, start_worker=False)
    with TestClient(app) as c:
        upload(c, [make_image(seed=i) for i in range(3)])
        bad = app.state.db.conn().execute("SELECT sha256, ext FROM photos ORDER BY id LIMIT 1").fetchone()
        reader.always_fail = f"{bad['sha256']}{bad['ext']}"
        app.state.worker.start()
        wait_done(c)
        s = c.get("/api/stats").json()
        assert s["ocr"] == {"done": 2, "error": 1}
        # reintento manual reinicia contador
        c.post("/api/process")
        reader.always_fail = None
        wait_done(c)
        assert c.get("/api/stats").json()["ocr"] == {"done": 3}


def test_worker_survives_db_errors(settings, monkeypatch):
    app = create_app(settings, reader=FlakyReader(), start_worker=False)
    w = app.state.worker
    boom = {"n": 0}
    orig = w._process_one

    def flaky():
        boom["n"] += 1
        if boom["n"] <= 2:
            raise RuntimeError("database is locked")
        return orig()
    monkeypatch.setattr(w, "_process_one", flaky)
    with TestClient(app) as c:
        upload(c, [make_image(seed=1)])
        w.start()
        wait_done(c, timeout=30)
        assert w.alive() and c.get("/api/stats").json()["ocr"] == {"done": 1}


def test_dead_worker_is_respawned_on_kick(settings):
    app = create_app(settings, reader=FlakyReader(), start_worker=True)
    with TestClient(app) as c:
        w = app.state.worker
        w._stop.set(); w._wake.set(); w.thread.join(3)   # simula la caída del hilo
        w._stop.clear()
        assert not w.alive()
        upload(c, [make_image(seed=2)])                   # kick() lo relanza
        wait_done(c, timeout=30)
        assert w.alive()


def test_upload_rejects_when_disk_almost_full(client, monkeypatch):
    monkeypatch.setattr(mainmod, "MIN_FREE_BYTES", 10 ** 18)
    r = client.post("/api/photos", files=[("files", ("a.jpg", make_image(seed=3), "image/jpeg"))])
    assert r.status_code == 507
    assert client.get("/api/stats").json()["photos"] == 0


def test_orphan_original_removed_when_thumb_fails(client, monkeypatch):
    from app import imaging
    monkeypatch.setattr(imaging, "make_thumb", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    res = client.post("/api/photos", files=[("files", ("a.jpg", make_image(seed=4), "image/jpeg"))]).json()["results"]
    assert res[0]["status"] == "rejected"
    s = client.app_.state.settings
    assert not list(s.originals.rglob("*.jpg")) and not list(s.tmp.glob("*"))


def test_bulk_delete_and_large_id_list(client):
    res = upload(client, [make_image(seed=i) for i in range(30)])
    ids = [r["id"] for r in res]
    r = client.post("/api/photos/delete", json={"ids": ids + list(range(1000, 6000))})
    assert r.json()["deleted"] == 30
    assert client.get("/api/stats").json()["photos"] == 0
    assert not list(client.app_.state.settings.originals.rglob("*.jpg"))


def test_deleting_photo_during_ocr_cannot_attach_its_bib_to_a_reused_id(client, monkeypatch):
    pid = upload(client, [make_image(seed=1)])[0]["id"]
    worker = client.app_.state.worker

    def read(_):
        assert client.delete(f"/api/photos/{pid}").status_code == 200
        assert upload(client, [make_image(seed=2)])[0]["id"] == pid
        return [Detection("123", "123", 0.95, [1, 1, 50, 50])]

    monkeypatch.setattr(worker.reader, "read", read)
    assert worker._process_one()
    photo = client.get(f"/api/photos/{pid}").json()
    assert photo["bibs"] == []
    assert photo["ocr_status"] == "pending"
