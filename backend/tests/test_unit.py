import io

import pytest

from app import imaging
from app.bibs import normalize_token, similar_numbers, box_ok, merge, Detection
from tests.conftest import make_image


@pytest.mark.parametrize("text,expected", [
    ("184", "184"), (" 18 4 ", "184"), ("1B4", "184"), ("I84", "184"),
    ("ABC", None), ("12AB", None), ("", None), ("123456", None), ("1234567", None), ("5", "5"),
])
def test_normalize_token(text, expected):
    assert normalize_token(text) == expected


def test_similar_numbers():
    assert similar_numbers("184", "194")
    assert similar_numbers("184", "18")
    assert similar_numbers("184", "1845")
    assert not similar_numbers("184", "184")
    assert not similar_numbers("184", "481")
    assert not similar_numbers("184", "1")


def test_box_filter():
    assert box_ok(120, 60, 1000)
    assert not box_ok(10, 8, 1000)       # diminuto
    assert not box_ok(600, 40, 1000)     # proporción de línea de texto


def test_merge_dedupes_same_number_overlap():
    a = Detection("184", "184", 0.9, [0, 0, 100, 50])
    b = Detection("184", "184", 0.8, [5, 5, 105, 55])
    c = Detection("185", "185", 0.8, [5, 5, 105, 55])
    out = merge([a, b, c])
    assert [d.number for d in out] == ["184", "185"]


def test_safe_name_strips_paths():
    assert imaging.safe_name("../../etc/passwd") == "passwd"
    assert imaging.safe_name("C:\\x\\y\\foto.jpg") == "foto.jpg"


def test_original_path_rejects_traversal(settings):
    with pytest.raises(ValueError):
        imaging.original_path(settings, "../../x", ".jpg")
    with pytest.raises(ValueError):
        imaging.original_path(settings, "a" * 64, ".exe")


def test_ingest_rejects_fake_image(settings):
    settings.ensure()
    with pytest.raises(imaging.InvalidImage):
        imaging.ingest(settings, io.BytesIO(b"not an image at all"), "x.jpg")
    assert list(settings.tmp.glob("*")) == []  # sin temporales huérfanos


def test_ingest_rejects_bad_extension_and_size(settings):
    settings.ensure()
    with pytest.raises(imaging.InvalidImage):
        imaging.ingest(settings, io.BytesIO(make_image()), "x.gif")
    settings.max_file_bytes = 100
    with pytest.raises(imaging.InvalidImage):
        imaging.ingest(settings, io.BytesIO(make_image()), "x.jpg")
