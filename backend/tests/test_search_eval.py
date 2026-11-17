"""Métricas de búsqueda (dorsal / cara / combinada) con valores calculados a mano."""
import io
import json

import numpy as np
import pytest

from app.evaluation import evaluate_search
from app.faces import to_blob
from tests.conftest import make_image


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_search_metrics_hand_computed(client):
    files = [("files", (f"{i}.jpg", io.BytesIO(make_image(seed=40 + i)), "image/jpeg")) for i in range(5)]
    p = [r["id"] for r in client.post("/api/photos", files=files).json()["results"]]
    c = client.app_.state.db.conn()
    rng = np.random.default_rng(3)
    me, other = unit(rng.normal(size=128)), unit(rng.normal(size=128))
    near_me = unit(me + 0.3 * unit(rng.normal(size=128)))

    def det(pid, n, conf):
        c.execute("INSERT INTO bib_detections(photo_id,number,raw_text,confidence,bbox) VALUES(?,?,?,?,?)",
                  (pid, n, n, conf, "[400,500,520,580]"))

    def face(pid, emb, bbox=(430, 330, 490, 400)):
        c.execute("INSERT INTO faces(photo_id,bbox,score,emb) VALUES(?,?,?,?)", (pid, json.dumps(list(bbox)), 0.9, to_blob(emb)))

    def label(pid, bibs, present, tags=()):
        c.execute("INSERT INTO gt_labels(photo_id,state,bibs,present,tags,split) VALUES(?,?,?,?,?,'test')",
                  (pid, "labeled" if bibs else "no_bib", json.dumps(bibs), json.dumps(present), json.dumps(list(tags))))

    det(p[0], "184", 0.95); face(p[0], me); label(p[0], ["184"], [])
    face(p[1], near_me); label(p[1], [], ["184"], ["perfil"])          # sale, dorsal tapado: solo la cara lo encuentra
    face(p[2], other); label(p[2], [], [])
    det(p[3], "184", 0.40); face(p[3], other); label(p[3], [], [])      # lectura errónea y dudosa del 184
    label(p[4], [], ["184"], ["gorra"])                                 # sale, pero no se detectó su cara

    m = evaluate_search(c, None, doubtful_below=0.85, faces_available=True)
    # verdad para el 184: {p0, p1, p4}
    assert m["queries"] == 1
    assert (m["per_mode"]["bib"]["tp"], m["per_mode"]["bib"]["fp"], m["per_mode"]["bib"]["fn"]) == (1, 1, 2)
    assert (m["per_mode"]["face"]["tp"], m["per_mode"]["face"]["fp"], m["per_mode"]["face"]["fn"]) == (2, 0, 1)
    assert (m["per_mode"]["combined"]["tp"], m["per_mode"]["combined"]["fp"], m["per_mode"]["combined"]["fn"]) == (2, 1, 1)
    assert m["per_mode"]["combined"]["precision"] == pytest.approx(2 / 3)
    assert m["per_mode"]["combined"]["recall"] == pytest.approx(2 / 3)
    assert m["face_only_pairs"] == 2 and m["face_only_recall"] == pytest.approx(0.5)
    assert m["by_tag"]["face"]["perfil"]["tp"] == 1 and m["by_tag"]["face"]["gorra"]["fn"] == 1

    # sin índice facial solo se informa del modo dorsal (no se inventan cifras de cara)
    m2 = evaluate_search(c, None, doubtful_below=0.85, faces_available=False)
    assert m2["modes"] == ["bib"] and m2["face_only_recall"] is None


def test_label_api_accepts_present_and_face_tags(client):
    pid = client.post("/api/photos", files=[("files", ("x.jpg", io.BytesIO(make_image(seed=60)), "image/jpeg"))]).json()["results"][0]["id"]
    r = client.put(f"/api/eval/labels/{pid}", json={"state": "no_bib", "present": ["184"], "tags": ["gafas", "gorra"]})
    assert r.status_code == 200
    lab = client.get("/api/eval/photos", params={"state": "labeled"}).json()["photos"][0]["label"]
    assert lab["present"] == ["184"] and lab["tags"] == ["gafas", "gorra"]
    assert client.put(f"/api/eval/labels/{pid}", json={"state": "no_bib", "present": ["x"]}).status_code == 422
