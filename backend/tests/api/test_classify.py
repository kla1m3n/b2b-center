from io import BytesIO

import pytest
from openpyxl import Workbook

from app import state
from app.schemas import ClassificationResult, Okpd2Ref, Regime


class FakePipeline:
    """Подменяет ИИ-конвейер: API-тесты проверяют HTTP-слой, а не модель."""

    def __init__(self):
        self.calls = []

    def classify_many(self, names, npa_version_id=None):
        self.calls.append((list(names), npa_version_id))
        return [ClassificationResult(input=n, okpd2=Okpd2Ref(code="26.20.11.110", title="Ноутбуки"),
                                     confidence=0.9, needs_review=False, verdict=Regime.restriction) for n in names]


@pytest.fixture
def fake_pipeline(monkeypatch):
    fake = FakePipeline()
    monkeypatch.setattr("app.api.classify.get_pipeline", lambda: fake)
    monkeypatch.setattr("app.celery_app.get_pipeline", lambda: fake)
    monkeypatch.setattr(state, "models_ready", True)
    return fake


@pytest.fixture
def celery_eager():
    from app.celery_app import celery

    celery.conf.task_always_eager = True
    yield
    celery.conf.task_always_eager = False


def test_classify_single(client, fake_pipeline):
    r = client.post("/api/classify", json={"name": "Ноутбук"})
    assert r.status_code == 200
    assert r.json()["okpd2"]["code"] == "26.20.11.110" and r.json()["input"] == "Ноутбук"


def test_classify_single_while_models_load_returns_503(client, fake_pipeline, monkeypatch):
    monkeypatch.setattr(state, "models_ready", False)
    r = client.post("/api/classify", json={"name": "Ноутбук"})
    assert r.status_code == 503 and "запускается" in r.json()["detail"]


def test_batch_limit(client, fake_pipeline):
    r = client.post("/api/classify/batch", json={"names": ["x"] * 101})
    assert r.status_code == 422 and "Не более 100" in r.text


def test_batch_empty_list(client, fake_pipeline):
    r = client.post("/api/classify/batch", json={"names": ["", "  "]})
    assert r.status_code == 422 and "пуст" in r.text


def test_batch_roundtrip_keeps_order_and_exports(client, fake_pipeline, celery_eager):
    job = client.post("/api/classify/batch", json={"names": ["ноутбук", "", "стул офисный"]}).json()
    body = client.get(f"/api/jobs/{job['job_id']}").json()
    assert body["status"] == "done" and body["total"] == 2 and body["done"] == 2
    assert [x["input"] for x in body["results"]] == ["ноутбук", "стул офисный"]
    x = client.get(f"/api/jobs/{job['job_id']}/export.xlsx")
    assert x.status_code == 200
    assert x.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_batch_from_excel_file(client, fake_pipeline, celery_eager):
    wb = Workbook()
    for row in (["Наименование"], ["Ноутбук"], ["Монитор"]):
        wb.active.append(row)
    buf = BytesIO()
    wb.save(buf)
    files = {"file": ("spec.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    job = client.post("/api/classify/batch", files=files).json()
    body = client.get(f"/api/jobs/{job['job_id']}").json()
    assert [x["input"] for x in body["results"]] == ["Ноутбук", "Монитор"]


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/00000000-0000-0000-0000-000000000000").status_code == 404


def test_job_uses_npa_version_snapshot_from_creation(client, fake_pipeline, celery_eager, session):
    from app.npa.service import get_active_version

    active = get_active_version(session)
    client.post("/api/classify/batch", json={"names": ["ноутбук"]})
    assert fake_pipeline.calls[-1][1] == (active.id if active else None)
