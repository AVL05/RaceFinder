"""Integración con el motor OCR real sobre imágenes SINTÉTICAS.
Comprueba que el pipeline completo funciona (import -> OCR -> índice -> búsqueda).
NO mide precisión sobre fotos reales de carreras: eso requiere un conjunto de evaluación (ver docs/EVALUATION.md)."""
import io

from tests.conftest import make_image, wait_done


def up(client, items):
    files = [("files", (n, io.BytesIO(b), "image/jpeg")) for n, b in items]
    return client.post("/api/photos", files=files).json()["results"]


def test_end_to_end_real_ocr(real_client):
    c = real_client
    ids = {k: up(c, [(f"{k}.jpg", img)])[0]["id"] for k, img in {
        "single": make_image(["184"], seed=1),
        "multi": make_image(["402", "77"], size=(2000, 1200), seed=2),
        "none": make_image([], seed=3),
    }.items()}
    s = wait_done(c)
    assert s["ocr"].get("done") == 3, s

    hit = c.get("/api/search", params={"bib": "184"}).json()
    assert [r["id"] for r in hit["results"]] == [ids["single"]]
    assert hit["results"][0]["evidence"][0]["bbox"][2] > hit["results"][0]["evidence"][0]["bbox"][0]

    # varios corredores en la misma foto
    for n in ("402", "77"):
        assert [r["id"] for r in c.get("/api/search", params={"bib": n}).json()["results"]] == [ids["multi"]]

    # foto sin dorsales y dorsal incorrecto: sin resultados
    assert c.get("/api/search", params={"bib": "999"}).json()["count"] == 0
    photos = {p["id"]: p for p in c.get("/api/photos").json()["photos"]}
    assert photos[ids["none"]]["bibs"] == []


def test_similar_number_is_not_exact(real_client):
    c = real_client
    pid = up(c, [("s.jpg", make_image(["184"], seed=4))])[0]["id"]
    wait_done(c)
    assert c.get("/api/search", params={"bib": "194"}).json()["count"] == 0
    r = c.get("/api/search", params={"bib": "194", "mode": "similar"}).json()
    assert r["count"] == 1 and r["results"][0]["match"] == "similar" and r["results"][0]["id"] == pid
