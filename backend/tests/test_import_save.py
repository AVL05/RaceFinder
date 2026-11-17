import os
import time

from .conftest import make_image


def write_photos(folder, n, start=0, ext="jpg"):
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (folder / f"IMG_{start + i:04d}.{ext}").write_bytes(make_image(seed=start + i, size=(800, 500)))


def wait_import(c, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        s = c.get("/api/import/status").json()
        if not s["running"]:
            return s
        time.sleep(0.1)
    raise AssertionError("timeout importando")


def test_import_folder_recursive_dedup_and_bad_files(client, tmp_path):
    src = tmp_path / "carrera"
    write_photos(src, 25)
    write_photos(src / "sub" / "otra", 5, start=100)
    (src / "roto.jpg").write_bytes(b"no soy una imagen")
    (src / "notas.txt").write_text("hola")
    (src / "vacio.png").write_bytes(b"")
    r = client.post("/api/import/folder", json={"path": str(src)})
    assert r.status_code == 200
    s = wait_import(client)
    assert (s["total"], s["added"], s["rejected"], s["duplicate"]) == (32, 30, 2, 0)
    assert s["linked"] + s["copied"] == 30
    assert client.get("/api/stats").json()["photos"] == 30
    # el original es idéntico byte a byte y la miniatura existe
    p = client.get("/api/photos?limit=1").json()["photos"][0]
    original = next(src.rglob(p["name"])).read_bytes()
    assert client.get(f"/api/photos/{p['id']}/original").content == original
    assert client.get(f"/api/photos/{p['id']}/thumb").status_code == 200
    # reimportar: todo duplicado, nada leído de nuevo
    client.post("/api/import/folder", json={"path": str(src)})
    s2 = wait_import(client)
    assert (s2["added"], s2["duplicate"]) == (0, 30)
    assert client.get("/api/stats").json()["photos"] == 30


def test_import_hardlink_does_not_duplicate_space_and_delete_keeps_source(client, tmp_path):
    src = tmp_path / "f"
    write_photos(src, 3)
    client.post("/api/import/folder", json={"path": str(src)})
    s = wait_import(client)
    if s["linked"]:  # solo si el sistema de archivos admite enlaces duros
        stt = client.app_.state.settings
        o = next(stt.originals.rglob("*.jpg"))
        assert o.stat().st_nlink >= 2
    ids = [p["id"] for p in client.get("/api/photos").json()["photos"]]
    client.post("/api/photos/delete", json={"ids": ids})
    assert len(list(src.glob("*.jpg"))) == 3 and all((f.stat().st_size > 0) for f in src.glob("*.jpg"))


def test_import_errors(client, tmp_path):
    assert client.post("/api/import/folder", json={"path": str(tmp_path / "no")}).status_code == 422
    assert client.post("/api/import/folder", json={"path": "relativa"}).status_code == 422


def test_import_cancel(client, tmp_path):
    src = tmp_path / "grande"
    write_photos(src, 60)
    client.post("/api/import/folder", json={"path": str(src)})
    client.post("/api/import/cancel")
    s = wait_import(client)
    assert s["cancelled"] is True and s["running"] is False
    client.post("/api/import/folder", json={"path": str(src)})  # se puede relanzar y completa
    s = wait_import(client)
    assert client.get("/api/stats").json()["photos"] == 60


def test_save_to_folder_no_overwrite_and_subfolder(client, tmp_path):
    src = tmp_path / "f"
    write_photos(src, 4)
    client.post("/api/import/folder", json={"path": str(src)})
    wait_import(client)
    ids = [p["id"] for p in client.get("/api/photos").json()["photos"]]
    dest = tmp_path / "salida"
    body = {"ids": ids, "dest": str(dest), "subfolder": "dorsal-123", "open_after": False}
    r = client.post("/api/export/save", json=body).json()
    assert (r["saved"], r["skipped"]) == (4, 0)
    out = sorted(p.name for p in (dest / "dorsal-123").iterdir())
    assert out == [f"IMG_000{i}.jpg" for i in range(4)]
    for f in (dest / "dorsal-123").iterdir():
        assert f.read_bytes() == (src / f.name).read_bytes()
    # segunda vez: ya están, no se duplican ni se sobrescriben
    r2 = client.post("/api/export/save", json=body).json()
    assert (r2["saved"], r2["skipped"]) == (0, 4)
    # mismo nombre pero otro contenido: se conserva el archivo del usuario
    (dest / "dorsal-123" / "IMG_0000.jpg").write_bytes(b"x")
    r3 = client.post("/api/export/save", json=body).json()
    assert r3["saved"] == 1 and (dest / "dorsal-123" / "IMG_0000_1.jpg").exists()
    assert (dest / "dorsal-123" / "IMG_0000.jpg").read_bytes() == b"x"
    assert not list((dest / "dorsal-123").glob(".*.part"))


def test_save_rejects_bad_dest_and_traversal(client, tmp_path):
    src = tmp_path / "f"
    write_photos(src, 1)
    client.post("/api/import/folder", json={"path": str(src)})
    wait_import(client)
    ids = [p["id"] for p in client.get("/api/photos").json()["photos"]]
    assert client.post("/api/export/save", json={"ids": ids, "dest": "relativa"}).status_code == 422
    r = client.post("/api/export/save", json={"ids": ids, "dest": str(tmp_path / "o"), "subfolder": "../../evil", "open_after": False}).json()
    from pathlib import Path
    assert Path(r["dest"]).parent == tmp_path / "o" and not (tmp_path / "evil").exists()
    assert client.post("/api/export/save", json={"ids": [999999], "dest": str(tmp_path / "o2")}).status_code == 404
