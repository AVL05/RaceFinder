import io
import time

import pytest
from fastapi.testclient import TestClient

from app.bibs import BibConfig, Detection
from app.evaluation import compute_metrics, split_for
from app.main import create_app
from tests.conftest import make_image


def item(i, truth, pred, tags=(), s=1.0):
    return {"id": i, "truth": set(truth), "pred": set(pred), "tags": list(tags), "seconds": s}


def test_metrics_hand_computed():
    m = compute_metrics([
        item(1, {"184", "77"}, {"184", "99"}, ["pequeno"], 1.0),
        item(2, {"402"}, {"402"}, [], 3.0),
        item(3, set(), {"55"}),      # sin dorsal legible, pero el OCR inventa uno
        item(4, set(), set()),
    ])
    b = m["per_bib"]
    assert (b["tp"], b["fp"], b["fn"]) == (2, 2, 1)
    assert b["precision"] == pytest.approx(0.5) and b["recall"] == pytest.approx(2 / 3)
    assert b["f1"] == pytest.approx(4 / 7)
    p = m["per_photo"]
    assert (p["all_bibs_found"], p["any_bib_found"], p["exact_set"]) == (1, 2, 1)
    assert p["false_alarm_photos"] == 1 and p["false_alarm_rate"] == 0.5
    assert m["timing"]["mean_s"] == pytest.approx(1.5) and m["timing"]["total_s"] == pytest.approx(6.0)
    assert m["by_tag"]["pequeno"]["fn"] == 1 and m["by_tag"]["pequeno"]["photos"] == 1
    assert {"photo_id": 1, "number": "77"} in m["errors"]["false_negatives"]


def test_metrics_near_miss_flagged_and_empty_safe():
    m = compute_metrics([item(1, {"184"}, {"194"})])
    assert m["errors"]["false_positives"][0]["near_miss_of_label"] is True
    assert m["per_bib"]["precision"] == 0 and m["per_bib"]["recall"] == 0
    e = compute_metrics([])
    assert e["per_bib"]["precision"] is None and e["timing"]["mean_s"] is None  # sin inventar números


def test_split_is_deterministic_and_roughly_30_70():
    shas = [f"{i * 2654435761 % 2**32:08x}" + "0" * 56 for i in range(1000)]
    assert [split_for(s) for s in shas] == [split_for(s) for s in shas]
    tune = sum(split_for(s) == "tune" for s in shas)
    assert 230 < tune < 370


def test_config_rejects_unknown_params():
    with pytest.raises(ValueError):
        BibConfig.from_dict({"nope": 1})
    assert BibConfig.from_dict({"min_conf": "0.7"}).min_conf == 0.7


class FakeReader:
    """Devuelve el dorsal que codifica el tamaño de la imagen: sin OCR real."""
    engine_name = "fake"
    ocr = object()

    def with_config(self, cfg):
        return self

    def read(self, path):
        time.sleep(0.01)
        return [Detection("184", "184", 0.9, [0, 0, 1, 1])]


@pytest.fixture
def eclient(settings):
    app = create_app(settings, reader=FakeReader(), start_worker=False)
    with TestClient(app) as c:
        yield c


def up(c, n):
    files = [("files", (f"{i}.jpg", io.BytesIO(make_image(seed=i)), "image/jpeg")) for i in range(n)]
    return [r["id"] for r in c.post("/api/photos", files=files).json()["results"]]


def test_label_validation_and_run_flow(eclient):
    ids = up(eclient, 12)
    eclient.app.state.db.conn().execute("UPDATE photos SET ocr_status='done'")  # sin worker: simula análisis terminado
    for bad in ({"state": "labeled", "bibs": []}, {"state": "labeled", "bibs": ["x"]}, {"state": "x"},
                {"state": "labeled", "bibs": ["1"], "tags": ["inventada"]}):
        assert eclient.put(f"/api/eval/labels/{ids[0]}", json=bad).status_code == 422
    for k, pid in enumerate(ids):
        body = {"state": "labeled", "bibs": ["184"]} if k % 2 == 0 else {"state": "no_bib"}
        assert eclient.put(f"/api/eval/labels/{pid}", json=body).status_code == 200
    s = eclient.get("/api/eval/summary").json()
    assert s["splits"]["tune"]["photos"] + s["splits"]["test"]["photos"] == 12 and s["unlabeled"] == 0
    split = "tune" if s["splits"]["tune"]["photos"] else "test"

    # 'test' exige confirmación explícita
    assert eclient.post("/api/eval/run", json={"split": "test"}).status_code == 409
    assert eclient.post("/api/eval/run", json={"split": split, "params": {"zzz": 1}, "confirm_test": True}).status_code == 422
    assert eclient.post("/api/eval/run", json={"split": split, "confirm_test": True}).status_code == 200
    for _ in range(100):
        st = eclient.get("/api/eval/status").json()
        if not st["running"]:
            break
        time.sleep(0.1)
    assert st["error"] is None and st["run_id"]
    run = eclient.get("/api/eval/runs").json()["runs"][0]
    m = run["metrics"]
    n_pos = m["photos_with_bibs"]; n_neg = m["photos_without_readable_bib"]
    assert m["per_bib"]["tp"] == n_pos and m["per_bib"]["fp"] == n_neg   # el lector falso siempre devuelve 184
    assert m["timing"]["mean_s"] >= 0.01 and run["params"]["min_conf"] == 0.5


def test_unlabeled_listing_and_delete(eclient):
    ids = up(eclient, 3)
    eclient.put(f"/api/eval/labels/{ids[0]}", json={"state": "no_bib"})
    assert eclient.get("/api/eval/photos", params={"state": "unlabeled"}).json()["total"] == 2
    eclient.delete(f"/api/eval/labels/{ids[0]}")
    assert eclient.get("/api/eval/photos", params={"state": "unlabeled"}).json()["total"] == 3
