from app.hardware import MAX_WORKERS, auto_workers


def test_cpu_solo_pocos_hilos():
    assert auto_workers("cpu", cores=16, ram_gb=32) == 3
    assert auto_workers("cpu", cores=4, ram_gb=16) == 2
    assert auto_workers("cpu", cores=2, ram_gb=16) == 1


def test_gpu_reparte_por_nucleos():
    assert auto_workers("cuda", cores=16, ram_gb=32) == 5
    assert auto_workers("cuda", cores=32, ram_gb=64) == 10
    assert auto_workers("cuda", cores=128, ram_gb=512) == MAX_WORKERS


def test_la_ram_pone_tope():
    assert auto_workers("cuda", cores=16, ram_gb=8) == 2     # (8-4)/1.5
    assert auto_workers("cuda", cores=16, ram_gb=4) == 1     # nunca menos de uno


def test_siempre_al_menos_uno():
    assert auto_workers("cpu", cores=1, ram_gb=1) == 1


def test_variable_de_entorno_manda(monkeypatch):
    from app.worker import Worker
    monkeypatch.setenv("RACEFINDER_WORKERS", "7")
    w = Worker(db=None, settings=None, reader=type("R", (), {"device": "cpu"})())
    assert (w.n_workers, w.workers_auto) == (7, False)
    monkeypatch.setenv("RACEFINDER_WORKERS", "basura")
    w = Worker(db=None, settings=None, reader=type("R", (), {"device": "cpu"})())
    assert w.workers_auto is True
