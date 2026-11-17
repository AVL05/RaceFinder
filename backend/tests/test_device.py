"""Selección de dispositivo CPU/GPU: lógica y respaldo a CPU (no mide velocidad: eso es tools/gpu_bench.py)."""
import pytest

from app import device
from app.bibs import BibReader


def test_cpu_only_onnxruntime_resolves_to_cpu(monkeypatch):
    monkeypatch.delenv("RACEFINDER_DEVICE", raising=False)
    monkeypatch.setattr(device, "onnx_providers", lambda: ["CPUExecutionProvider"])
    assert device.resolve_ocr_device() == "cpu"


@pytest.mark.parametrize("providers,req,expected", [
    (["CUDAExecutionProvider", "CPUExecutionProvider"], "auto", "cuda"),
    (["DmlExecutionProvider", "CPUExecutionProvider"], "auto", "dml"),
    (["CUDAExecutionProvider", "DmlExecutionProvider"], "auto", "cuda"),
    (["CUDAExecutionProvider", "CPUExecutionProvider"], "cpu", "cpu"),
    (["DmlExecutionProvider", "CPUExecutionProvider"], "cuda", "cpu"),   # pedida pero no disponible: CPU
])
def test_ocr_device_choice(monkeypatch, providers, req, expected):
    monkeypatch.setattr(device, "onnx_providers", lambda: providers)
    monkeypatch.setattr(device, "preload_cuda_libs", lambda: None)
    assert device.resolve_ocr_device(req) == expected


def test_invalid_env_value_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("RACEFINDER_DEVICE", "tpu")
    monkeypatch.setattr(device, "onnx_providers", lambda: ["CPUExecutionProvider"])
    assert device.resolve_ocr_device() == "cpu"


def test_ocr_kwargs():
    assert device.ocr_kwargs("cpu") == {}
    assert device.ocr_kwargs("cuda") == {"det_use_cuda": True, "cls_use_cuda": True, "rec_use_cuda": True}
    assert device.ocr_kwargs("dml") == {"det_use_dml": True, "cls_use_dml": True, "rec_use_dml": True}


def test_bib_reader_forced_cpu_and_with_config_keeps_device():
    r = BibReader(device="cpu")
    assert r.device == "cpu"
    assert r.with_config(r.cfg).device == "cpu"
