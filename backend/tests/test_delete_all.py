import io
import json

import numpy as np

from app.faces import to_blob
from tests.conftest import make_image


def test_delete_all_photos_removes_everything_but_settings(client, settings):
    files = [("files", (f"{i}.jpg", io.BytesIO(make_image(["184"], seed=70 + i)), "image/jpeg")) for i in range(4)]
    ids = [r["id"] for r in client.post("/api/photos", files=files).json()["results"]]
    c = client.app_.state.db.conn()
    marker = np.full(128, 0.0883883, dtype=np.float32)  # vector reconocible para buscarlo en disco
    for pid in ids:
        c.execute("INSERT INTO bib_detections(photo_id,number,raw_text,confidence,bbox) VALUES(?,?,?,?,?)",
                  (pid, "184", "184", 0.95, "[400,300,560,520]"))
        c.execute("INSERT INTO faces(photo_id,bbox,score,emb) VALUES(?,?,?,?)", (pid, "[430,100,490,170]", 0.9, to_blob(marker)))
        c.execute("INSERT INTO gt_labels(photo_id,state,bibs,tags,split) VALUES(?,?,?,?,'test')", (pid, "labeled", '["184"]', "[]"))
    for pid in ids:  # generar derivados: vista previa y recorte del dorsal
        client.get(f"/api/photos/{pid}/preview")
    bid = client.get("/api/search", params={"bib": "184"}).json()["results"][0]["evidence"][0]["bib_id"]
    assert client.get(f"/api/bibs/{bid}/crop").status_code == 200
    client.put("/api/settings", json={"mode": "fast", "min_number": 1, "max_number": 2000})
    assert any(settings.previews.rglob("*.jpg")) and any(settings.crops.rglob("*.jpg"))

    # sin la palabra de confirmación no se borra nada
    assert client.post("/api/photos/delete-all", json={"confirm": "si"}).status_code == 422
    assert client.get("/api/stats").json()["photos"] == 4

    r = client.post("/api/photos/delete-all", json={"confirm": "ELIMINAR"})
    assert r.status_code == 200 and r.json()["deleted"] == 4

    st = client.get("/api/stats").json()
    assert st["photos"] == 0 and st["faces"]["count"] == 0 and st["distinct_bibs"] == 0
    for t in ("photos", "bib_detections", "faces", "gt_labels"):
        assert c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
    for d in (settings.originals, settings.thumbs, settings.previews, settings.crops):
        assert d.exists() and not any(d.rglob("*")), d                  # carpetas vacías pero presentes
    blob = to_blob(marker)[:64]
    for f in settings.data_dir.glob("racefinder.sqlite3*"):
        assert blob not in f.read_bytes(), f.name                        # tampoco en el diario WAL
    s = client.get("/api/settings").json()
    assert (s["mode"], s["min_number"], s["max_number"]) == ("fast", 1, 2000)   # los ajustes se conservan

    # la biblioteca sigue funcionando: se puede volver a importar (también las mismas fotos)
    again = client.post("/api/photos", files=[("files", ("0.jpg", io.BytesIO(make_image(["184"], seed=70)), "image/jpeg"))]).json()
    assert again["results"][0]["status"] == "added"
    assert client.get(f"/api/photos/{again['results'][0]['id']}/thumb").status_code == 200
