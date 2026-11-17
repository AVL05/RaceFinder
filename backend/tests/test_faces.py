"""Reconocimiento facial: asociación cara-dorsal, búsqueda, consentimiento y borrado de datos biométricos.
Los vectores se insertan directamente: estos tests comprueban la lógica, NO la precisión de los modelos."""
import io
import json

import numpy as np
import pytest

from app.faces import associate, to_blob, MATCH_THRESHOLD
from tests.conftest import make_image


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def F(bbox):
    return {"bbox": bbox}


# ---------------- asociación en fotos con varios corredores ----------------

def test_associate_picks_face_above_bib():
    bib = [400, 500, 520, 580]
    mine, other, below = F([430, 330, 490, 400]), F([900, 330, 960, 400]), F([430, 700, 490, 770])
    assert associate(bib, [other, below, mine]) is mine
    assert associate(bib, [other, below]) is None  # no se inventa una asociación


def test_associate_runners_side_by_side_each_gets_own_face():
    left_bib, right_bib = [300, 500, 420, 580], [560, 500, 680, 580]
    left, right = F([330, 330, 390, 400]), F([590, 330, 650, 400])
    assert associate(left_bib, [left, right]) is left
    assert associate(right_bib, [left, right]) is right


def test_associate_prefers_front_runner_over_smaller_face_behind():
    bib = [400, 500, 520, 580]                       # corredor en primer plano
    front = F([425, 320, 495, 400])                  # su cara, grande y justo encima
    behind = F([450, 260, 470, 282])                 # cara pequeña de alguien al fondo, también alineada
    assert associate(bib, [behind, front]) is front


def test_associate_rejects_implausible_scale_and_distance():
    bib = [400, 500, 520, 580]
    huge = F([300, 0, 620, 400])                     # 5x el alto del dorsal: no es su cara
    far_above = F([440, 0, 480, 40])                 # demasiado lejos para un torso
    assert associate(bib, [huge]) is None
    assert associate(bib, [far_above]) is None


def test_associate_bib_without_visible_face_returns_none():
    assert associate([400, 500, 520, 580], []) is None


# ---------------- flujo completo de la API ----------------

def setup(client, n=5):
    files = [("files", (f"{i}.jpg", io.BytesIO(make_image(seed=i)), "image/jpeg")) for i in range(n)]
    ids = [r["id"] for r in client.post("/api/photos", files=files).json()["results"]]
    c = client.app_.state.db.conn()
    rng = np.random.default_rng(0)
    me, other = unit(rng.normal(size=128)), unit(rng.normal(size=128))
    near_me = unit(me + 0.3 * unit(rng.normal(size=128)))

    def face(pid, bbox, emb):
        return c.execute("INSERT INTO faces(photo_id,bbox,score,emb) VALUES(?,?,?,?)",
                         (pid, json.dumps(bbox), 0.9, to_blob(emb))).lastrowid

    def bib(pid, n, conf):
        c.execute("INSERT INTO bib_detections(photo_id,number,raw_text,confidence,bbox) VALUES(?,?,?,?,?)",
                  (pid, n, n, conf, "[400,500,520,580]"))
    bib(ids[0], "184", 0.95)
    f_me = face(ids[0], [430, 330, 490, 400], me)
    face(ids[0], [900, 330, 960, 400], other)          # otra persona al lado
    face(ids[1], [100, 100, 160, 170], near_me)        # yo, sin dorsal legible
    face(ids[2], [100, 100, 160, 170], other)          # otra persona
    bib(ids[3], "184", 0.40)                            # lectura DUDOSA del 184...
    f_doubt = face(ids[3], [430, 330, 490, 400], other)  # ...sobre otra persona
    # ids[4]: sin dorsal ni cara
    c.execute("UPDATE photos SET face_status='done', ocr_status='done'")
    return ids, f_me, f_doubt


def enable(client):
    r = client.put("/api/settings", json={"mode": "balanced", "faces_enabled": True, "face_consent": True})
    assert r.status_code == 200 and r.json()["faces_enabled"] is True and r.json()["faces_consent_at"]


def test_consent_required_at_api_level(client):
    setup(client)
    assert client.get("/api/faces/for-bib", params={"bib": "184"}).status_code == 409
    r = client.put("/api/settings", json={"mode": "balanced", "faces_enabled": True})
    assert r.status_code == 422                          # sin consentimiento explícito no se activa
    assert client.get("/api/settings").json()["faces_enabled"] is False
    enable(client)
    # cambiar otros ajustes con la función ya activa no vuelve a pedir el consentimiento
    assert client.put("/api/settings", json={"mode": "fast", "faces_enabled": True}).status_code == 200


def test_doubtful_bib_does_not_preselect_face(client):
    ids, f_me, f_doubt = setup(client)
    enable(client)
    faces = {f["id"]: f for f in client.get("/api/faces/for-bib", params={"bib": "184"}).json()["faces"]}
    assert faces[f_me]["preselect"] is True
    assert faces[f_doubt]["associated"] is True and faces[f_doubt]["preselect"] is False


def test_face_search_finds_photo_without_bib_and_not_others(client):
    ids, f_me, _ = setup(client)
    enable(client)
    r = client.post("/api/faces/search", json={"face_ids": [f_me]}).json()
    found = {x["id"]: x["face"] for x in r["results"]}
    assert ids[0] in found and ids[1] in found
    assert ids[2] not in found and ids[3] not in found and ids[4] not in found
    assert all(MATCH_THRESHOLD <= f["similarity"] <= 1.0001 for f in found.values())


def test_catalog_keeps_photos_without_any_match(client):
    ids, f_me, _ = setup(client)
    enable(client)
    client.post("/api/faces/search", json={"face_ids": [f_me]})
    allp = client.get("/api/photos", params={"limit": 100}).json()
    assert allp["total"] == 5 and {p["id"] for p in allp["photos"]} == set(ids)   # nada desaparece
    nob = client.get("/api/photos", params={"filter": "no_bib"}).json()
    assert ids[4] in {p["id"] for p in nob["photos"]} and ids[1] in {p["id"] for p in nob["photos"]}
    # una lectura dudosa sigue apareciendo en la búsqueda, marcada para revisar
    s = client.get("/api/search", params={"bib": "184"}).json()
    assert {x["id"]: x["match"] for x in s["results"]} == {ids[0]: "exact", ids[3]: "doubtful"}


def test_consistency_is_leave_one_out(client):
    """Con 3 caras asociadas (el mínimo), la intrusa se marca. Con la media antigua, que incluía a la propia cara,
    su similitud salía 0,48 (por encima del umbral) y NO se marcaba; dejándola fuera sale 0,04."""
    files = [("files", (f"c{i}.jpg", io.BytesIO(make_image(seed=20 + i)), "image/jpeg")) for i in range(3)]
    ids = [r["id"] for r in client.post("/api/photos", files=files).json()["results"]]
    c = client.app_.state.db.conn()
    rng = np.random.default_rng(5)
    me = unit(rng.normal(size=128))
    embs = [unit(me + 0.2 * unit(rng.normal(size=128))) for _ in range(2)] + [unit(rng.normal(size=128))]
    fids = []
    for pid, e in zip(ids, embs):
        c.execute("INSERT INTO bib_detections(photo_id,number,raw_text,confidence,bbox) VALUES(?,?,?,?,?)",
                  (pid, "77", "77", 0.99, "[400,500,520,580]"))
        fids.append(c.execute("INSERT INTO faces(photo_id,bbox,score,emb) VALUES(?,?,?,?)",
                              (pid, "[430,330,490,400]", 0.9, to_blob(e))).lastrowid)
    enable(client)
    faces = {f["id"]: f for f in client.get("/api/faces/for-bib", params={"bib": "77"}).json()["faces"]}
    assert [faces[i]["consistent"] for i in fids] == [True, True, False]
    assert faces[fids[2]]["preselect"] is False


def test_delete_all_biometric_data(client, settings):
    ids, f_me, _ = setup(client)
    enable(client)
    assert client.get(f"/api/faces/{f_me}/crop").status_code == 200
    assert client.get(f"/api/faces/{f_me}/crop").headers["cache-control"] == "no-store"
    crops_before = list(settings.crops.rglob("*.jpg"))
    assert crops_before
    me_bytes = to_blob(unit(np.random.default_rng(0).normal(size=128)))[:64]
    on_disk = b"".join(f.read_bytes() for f in settings.data_dir.glob("racefinder.sqlite3*"))
    assert me_bytes in on_disk                                  # control: antes del borrado SÍ está

    assert client.delete("/api/faces").json()["deleted"] == 5
    c = client.app_.state.db.conn()
    assert c.execute("SELECT COUNT(*) FROM faces").fetchone()[0] == 0
    assert list(settings.crops.rglob("*.jpg")) == []          # recortes de caras borrados del disco
    st = client.get("/api/settings").json()
    assert st["faces_enabled"] is False and st["faces_consent_at"] is None
    assert client.get(f"/api/faces/{f_me}/crop").status_code == 409   # nada accesible tras el borrado
    # el vector borrado no sobrevive en el archivo de la base de datos ni en su diario WAL
    for f in settings.data_dir.glob("racefinder.sqlite3*"):
        assert me_bytes not in f.read_bytes(), f.name
    # los datos no biométricos siguen intactos
    assert client.get("/api/photos").json()["total"] == 5
