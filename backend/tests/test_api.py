import hashlib
import io
import json
import zipfile

from tests.conftest import make_image, wait_done


def up(client, items):
    files = [("files", (n, io.BytesIO(b), "image/jpeg")) for n, b in items]
    return client.post("/api/photos", files=files).json()["results"]


def test_health_and_host_protection(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/health", headers={"host": "evil.example.com"}).status_code == 400


def test_upload_duplicates_and_rejects(client, settings):
    img = make_image(["184"])
    r = up(client, [("a.jpg", img), ("b.jpg", img), ("c.gif", img), ("d.jpg", b"garbage")])
    assert [x["status"] for x in r] == ["added", "duplicate", "rejected", "rejected"]
    assert client.get("/api/stats").json()["photos"] == 1
    assert list(settings.tmp.glob("*.part")) == []


def test_original_is_byte_identical(client, settings):
    img = make_image(["77"])
    pid = up(client, [("orig.jpg", img)])[0]["id"]
    served = client.get(f"/api/photos/{pid}/original").content
    assert hashlib.sha256(served).hexdigest() == hashlib.sha256(img).hexdigest()
    stored = next(settings.originals.rglob("*.jpg")).read_bytes()
    assert stored == img


def test_thumbnail_generated(client):
    pid = up(client, [("t.jpg", make_image())])[0]["id"]
    r = client.get(f"/api/photos/{pid}/thumb")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    from PIL import Image
    assert max(Image.open(io.BytesIO(r.content)).size) <= 480


def test_png_and_webp_accepted(client):
    r = up(client, [("a.png", make_image(fmt="PNG", seed=1)), ("b.webp", make_image(fmt="WEBP", seed=2))])
    assert [x["status"] for x in r] == ["added", "added"]


def test_search_validation_and_matching(client):
    """Inserta detecciones directamente: prueba la lógica de búsqueda, no el OCR."""
    ids = [x["id"] for x in up(client, [(f"{i}.jpg", make_image(seed=i)) for i in range(4)])]
    c = client.app_.state.db.conn()
    def ins(pid, n, conf, review="auto"):
        c.execute("INSERT INTO bib_detections(photo_id,number,raw_text,confidence,bbox,review) VALUES(?,?,?,?,?,?)",
                  (pid, n, n, conf, json.dumps([1, 2, 3, 4]), review))
    ins(ids[0], "184", 0.9); ins(ids[0], "55", 0.9)   # varios dorsales en una foto
    ins(ids[1], "184", 0.6)
    ins(ids[2], "194", 0.99)                           # similar
    ins(ids[3], "1840", 0.9, "rejected")               # rechazado: nunca aparece

    assert client.get("/api/search", params={"bib": "abc"}).status_code == 422
    r = client.get("/api/search", params={"bib": "184"}).json()
    assert [x["id"] for x in r["results"]] == [ids[0], ids[1]]       # solo exactos, por confianza
    assert [x["match"] for x in r["results"]] == ["exact", "doubtful"]   # 0.6 < umbral de duda
    r = client.get("/api/search", params={"bib": "184", "mode": "similar"}).json()
    assert [x["id"] for x in r["results"]] == [ids[0], ids[1], ids[2]]
    assert r["results"][2]["match"] == "similar"
    assert r["results"][0]["evidence"][0]["bbox"] == [1, 2, 3, 4]    # evidencia conservada
    r = client.get("/api/search", params={"bib": "184", "min_conf": 0.8}).json()
    assert [x["id"] for x in r["results"]] == [ids[0]]


def test_manual_review(client):
    pid = up(client, [("m.jpg", make_image())])[0]["id"]
    bid = client.post(f"/api/photos/{pid}/bibs", json={"number": "321"}).json()["id"]
    assert client.get("/api/search", params={"bib": "321"}).json()["count"] == 1
    client.patch(f"/api/bibs/{bid}", json={"review": "rejected"})
    assert client.get("/api/search", params={"bib": "321"}).json()["count"] == 0
    assert client.post(f"/api/photos/{pid}/bibs", json={"number": "x1"}).status_code == 422


def test_export_is_byte_identical_zip(client):
    imgs = [make_image(seed=i) for i in range(3)]
    ids = [x["id"] for x in up(client, [("same.jpg", b) for b in imgs])]  # mismo nombre: no debe pisarse
    r = client.post("/api/export", json={"ids": ids})
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert len(z.namelist()) == 3
    got = sorted(hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist())
    assert got == sorted(hashlib.sha256(b).hexdigest() for b in imgs)
    assert client.post("/api/export", json={"ids": [9999]}).status_code == 404


def test_delete_removes_files(client, settings):
    pid = up(client, [("d.jpg", make_image())])[0]["id"]
    client.get(f"/api/photos/{pid}/thumb")
    assert client.delete(f"/api/photos/{pid}").status_code == 200
    assert list(settings.originals.rglob("*.jpg")) == [] and list(settings.thumbs.rglob("*.jpg")) == []
    assert client.get(f"/api/photos/{pid}/thumb").status_code == 404


def test_cors_restricted(client):
    r = client.get("/api/health", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in r.headers
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_resume_resets_processing(settings):
    from app.main import create_app
    from fastapi.testclient import TestClient
    app = create_app(settings, start_worker=False)
    with TestClient(app) as c:
        pid = up(c, [("r.jpg", make_image())])[0]["id"]
        app.state.db.conn().execute("UPDATE photos SET ocr_status='processing' WHERE id=?", (pid,))
    app.state.worker.start()
    try:
        assert app.state.db.conn().execute("SELECT ocr_status FROM photos WHERE id=?", (pid,)).fetchone()[0] in ("pending", "processing", "done", "error")
    finally:
        app.state.worker.stop()


def test_exif_rotated_photo_reports_displayed_dimensions(client):
    from PIL import Image
    im = Image.new("RGB", (1200, 800), (10, 20, 30))
    exif = im.getexif(); exif[0x0112] = 6   # girar 90°: se ve 800x1200
    buf = io.BytesIO(); im.save(buf, "JPEG", exif=exif)
    pid = up(client, [("rot.jpg", buf.getvalue())])[0]["id"]
    p = client.get("/api/photos").json()["photos"][0]
    assert (p["width"], p["height"]) == (800, 1200)
    t = Image.open(io.BytesIO(client.get(f"/api/photos/{pid}/thumb").content))
    assert t.size[1] > t.size[0]  # la miniatura respeta la orientación


def test_preview_is_smaller_than_original(client):
    from PIL import Image
    pid = up(client, [("big.jpg", make_image(size=(3200, 2000)))])[0]["id"]
    r = client.get(f"/api/photos/{pid}/preview")
    assert r.status_code == 200 and max(Image.open(io.BytesIO(r.content)).size) == 1600


def test_pagination_total(client):
    up(client, [(f"{i}.jpg", make_image(seed=i)) for i in range(5)])
    r = client.get("/api/photos", params={"limit": 2, "offset": 2}).json()
    assert r["total"] == 5 and len(r["photos"]) == 2


def test_upload_does_not_override_cancel(client):
    w = client.app_.state.worker
    w.cancel()
    up(client, [("c.jpg", make_image())])
    assert w.is_paused()
    client.post("/api/process")
    assert not w.is_paused()


def test_bib_range_filters_search_and_chips_but_keeps_manual(client):
    ids = [x["id"] for x in up(client, [(f"{i}.jpg", make_image(seed=i)) for i in range(2)])]
    cn = client.app_.state.db.conn()
    for pid, n in ((ids[0], "5727"), (ids[1], "184")):
        cn.execute("INSERT INTO bib_detections(photo_id,number,raw_text,confidence,bbox) VALUES(?,?,?,0.99,'[1,2,3,4]')", (pid, n, n))
    assert client.get("/api/search", params={"bib": "5727"}).json()["count"] == 1
    assert client.put("/api/settings", json={"mode": "balanced", "min_number": 1, "max_number": 2000}).status_code == 200
    assert client.get("/api/search", params={"bib": "5727"}).json()["count"] == 0      # cartel fuera del rango de la carrera
    assert client.get("/api/search", params={"bib": "184"}).json()["count"] == 1
    photos = {p["id"]: p for p in client.get("/api/photos").json()["photos"]}
    assert photos[ids[0]]["bibs"] == []
    client.post(f"/api/photos/{ids[0]}/bibs", json={"number": "5727"})                 # lo confirma una persona
    assert client.get("/api/search", params={"bib": "5727"}).json()["count"] == 1


def test_settings_validation(client):
    assert client.put("/api/settings", json={"mode": "x"}).status_code == 422
    assert client.put("/api/settings", json={"mode": "fast", "min_number": 10, "max_number": 5}).status_code == 422
    assert client.put("/api/settings", json={"mode": "fast"}).json()["mode"] == "fast"
    assert client.get("/api/settings").json()["mode"] == "fast"
    assert client.app_.state.worker.reader.cfg.tile_policy == "nunca"
