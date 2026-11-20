import csv
import hashlib
import io
import sqlite3
import time

import numpy as np

from app.db import Database, SCHEMA
from tests.conftest import make_image


def upload(client, name, image, album=None):
    params = {"album": album} if album is not None else {}
    response = client.post("/api/photos", params=params, files={"files": (name, image, "image/jpeg")})
    assert response.status_code == 200
    return response.json()["results"][0]


def make_album(client, name):
    response = client.post("/api/albums", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def test_album_scopes_duplicate_import_search_and_index(client):
    first = make_album(client, "Media maratón")
    second = make_album(client, "Trail")
    image = make_image(seed=1)
    pid = upload(client, "llegada.jpg", image, first)["id"]
    other = upload(client, "meta.jpg", make_image(seed=2), second)["id"]
    for photo in (pid, other):
        assert client.post(f"/api/photos/{photo}/bibs", json={"number": "184"}).status_code == 200
    for album, photo in ((first, pid), (second, other)):
        assert [p["id"] for p in client.get("/api/photos", params={"album": album}).json()["photos"]] == [photo]
        assert [p["id"] for p in client.get("/api/search", params={"bib": "184", "album": album}).json()["results"]] == [photo]
        assert client.get("/api/bibs/index", params={"album": album}).json()["bibs"][0]["photos"] == 1
        assert client.get("/api/stats", params={"album": album}).json()["photos"] == 1

    fingerprint = {"size": len(image), "head": hashlib.sha256(image[:65536]).hexdigest()}
    for album, expected in ((first, True), (second, False)):
        assert client.post("/api/photos/known", params={"album": album}, json={"items": [fingerprint]}).json() == {"known": [expected]}
    assert upload(client, "copia.jpg", image, second) == {"id": pid, "name": "copia.jpg", "status": "duplicate"}
    assert client.get("/api/stats").json()["photos"] == 2
    assert client.get("/api/stats", params={"album": second}).json()["photos"] == 2


def test_album_lifecycle_and_non_destructive_membership(client):
    album = make_album(client, "  Local  ")
    assert client.post("/api/albums", json={"name": "local"}).status_code == 409
    assert client.patch(f"/api/albums/{album}", json={"name": "Llegada"}).json()["name"] == "Llegada"
    pid = upload(client, "foto.jpg", make_image())["id"]
    url = f"/api/albums/{album}/photos"
    for action, changed in (("add", 1), ("add", 0), ("remove", 1), ("remove", 0), ("add", 1)):
        assert client.post(url, json={"ids": [pid, 9999, pid], "action": action}).json()["changed"] == changed
    assert client.get("/api/albums").json()["albums"] == [
        {"id": album, "name": "Llegada", "photos": 1, "min_number": None, "max_number": None},
    ]
    assert client.delete(f"/api/albums/{album}").status_code == 200
    assert client.get("/api/photos", params={"album": album}).status_code == 404
    assert client.get(f"/api/photos/{pid}/original").status_code == 200
    assert make_album(client, "Nueva") > album


def test_native_folder_reuses_same_original_in_an_album(client, tmp_path):
    album = make_album(client, "Evento")
    image = make_image()
    pid = upload(client, "original.jpg", image)["id"]
    folder = tmp_path / "race"
    folder.mkdir()
    (folder / "misma.jpg").write_bytes(image)
    (folder / "nueva.jpg").write_bytes(make_image(seed=1))
    assert client.post("/api/import/folder", json={"path": str(folder), "album": album}).status_code == 200
    deadline = time.monotonic() + 10
    while (job := client.get("/api/import/status").json())["running"] and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not job["running"]
    assert (job["added"], job["duplicate"], job["rejected"]) == (1, 1, 0)
    assert pid in {p["id"] for p in client.get("/api/photos", params={"album": album}).json()["photos"]}
    assert client.get("/api/stats", params={"album": album}).json()["photos"] == 2


def test_favorites_name_sort_selection_and_csv_share_the_filter(client):
    album = make_album(client, "@Meta")
    first = upload(client, "=ÁGUILA.jpg", make_image(seed=11), album)["id"]
    second = upload(client, "Amanecer.jpg", make_image(seed=12), album)["id"]
    third = upload(client, "Águila otra.jpg", make_image(seed=13))["id"]
    assert client.put("/api/photos/favorites", json={"ids": [first, third], "favorite": True}).json() == {"changed": 2}
    assert client.put("/api/photos/favorites", json={"ids": [first], "favorite": True}).json() == {"changed": 0}
    assert client.get(f"/api/photos/{first}").json()["favorite"]
    assert [p["id"] for p in client.get("/api/photos", params={"sort": "name"}).json()["photos"]] == [first, second, third]
    params = {"album": album, "filter": "favorites", "filename": "Águila", "sort": "oldest"}
    assert [p["id"] for p in client.get("/api/photos", params=params).json()["photos"]] == [first]
    assert [p["id"] for p in client.get("/api/photos/selection", params=params).json()["photos"]] == [first]
    assert client.post(f"/api/photos/{first}/bibs", json={"number": "184"}).status_code == 200
    response = client.get("/api/export/catalog.csv", params=params)
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert [(r["Archivo"], r["Álbum"], r["Dorsales"], r["Favorita"]) for r in rows] == [("'=ÁGUILA.jpg", "'@Meta", "184", "Sí")]


def test_review_queue_clears_after_confirming_and_respects_albums(client):
    album = make_album(client, "Meta")
    photo = upload(client, "dudosa.jpg", make_image(), album)["id"]
    detection = client.app_.state.db.conn().execute(
        "INSERT INTO bib_detections(photo_id,number,raw_text,confidence,bbox) VALUES(?,'184','184',0.51,'[1,2,3,4]')",
        (photo,),
    ).lastrowid
    params = {"album": album, "filter": "review"}
    assert client.get("/api/photos", params=params).json()["total"] == 1
    assert client.get("/api/stats", params={"album": album}).json()["needs_review"] == 1
    assert client.patch(f"/api/bibs/{detection}", json={"review": "confirmed"}).status_code == 200
    assert client.get("/api/photos", params=params).json()["total"] == 0


def test_album_range_overrides_gallery_search_and_csv_without_hiding_manual_bibs(client):
    photo = upload(client, "dorsales.jpg", make_image())["id"]
    album_data = {"name": "Rango propio", "ids": [photo], "min_number": 1, "max_number": 500}
    album = client.post("/api/albums", json=album_data).json()
    assert album["photos"] == 1
    assert client.put("/api/settings", json={"min_number": 1000}).status_code == 200
    conn = client.app_.state.db.conn()
    for number in ("184", "2025"):
        conn.execute("INSERT INTO bib_detections(photo_id,number,raw_text,confidence,bbox) VALUES(?,?,?,0.95,'[1,2,3,4]')",
                     (photo, number, number))
    assert client.post(f"/api/photos/{photo}/bibs", json={"number": "900"}).status_code == 200
    params = {"album": album["id"]}
    expected = {"184", "900"}
    assert {r["number"] for r in client.get(f"/api/photos/{photo}", params=params).json()["bibs"]} == expected
    assert {r["number"] for r in client.get("/api/bibs/index", params=params).json()["bibs"]} == expected
    assert client.get("/api/search", params={**params, "bib": "184"}).json()["count"] == 1
    assert client.get("/api/search", params={**params, "bib": "2025"}).json()["count"] == 0
    assert client.get("/api/search", params={"bib": "2025"}).json()["count"] == 1
    csv_export = client.get("/api/export/catalog.csv", params=params).content.decode("utf-8-sig")
    assert next(csv.DictReader(io.StringIO(csv_export), delimiter=";"))["Dorsales"] == "184, 900"


def test_face_references_and_results_are_scoped_to_album(client):
    album = make_album(client, "Carrera")
    pids = [upload(client, f"{n}.jpg", make_image(seed=n), album if n == 0 else None)["id"] for n in range(2)]
    assert client.put("/api/settings", json={"faces_enabled": True, "face_consent": True}).status_code == 200
    vec = np.eye(1, 128, dtype=np.float32).tobytes()
    conn = client.app_.state.db.conn()
    faces = []
    for pid in pids:
        assert client.post(f"/api/photos/{pid}/bibs", json={"number": "184"}).status_code == 200
        faces.append(conn.execute("INSERT INTO faces(photo_id,bbox,score,emb) VALUES(?,'[1,2,3,4]',1.0,?)", (pid, vec)).lastrowid)
    params = {"album": album}
    candidates = client.get("/api/faces/for-bib", params={**params, "bib": "184"}).json()["faces"]
    assert [face["id"] for face in candidates] == [faces[0]]
    results = client.post("/api/faces/search", params=params, json={"face_ids": [faces[0]]}).json()["results"]
    assert [p["id"] for p in results] == [pids[0]]
    assert client.post("/api/faces/search", params=params, json={"face_ids": [faces[1]]}).status_code == 404


def test_existing_photo_rows_are_migrated_without_reimport(tmp_path):
    filename = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(filename) as conn:
        conn.executescript(SCHEMA.replace("  favorite INTEGER NOT NULL DEFAULT 0,\n", ""))
        conn.execute("INSERT INTO photos(sha256,original_name,ext,size) VALUES('abc','legado.jpg','.jpg',10)")
    database = Database(filename)
    assert tuple(database.conn().execute("SELECT original_name, favorite FROM photos").fetchone()) == ("legado.jpg", 0)
