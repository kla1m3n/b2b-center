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


def _sheets(response) -> list[str]:
    from openpyxl import load_workbook

    return load_workbook(BytesIO(response.content)).sheetnames


def _is_docx(response) -> bool:
    import zipfile

    with zipfile.ZipFile(BytesIO(response.content)) as z:
        return "word/document.xml" in z.namelist()


def test_job_has_summary_and_reports(client, fake_pipeline, celery_eager):
    job = client.post("/api/classify/batch", json={"names": ["ноутбук", "стул офисный", "монитор", "мышь"]}).json()
    body = client.get(f"/api/jobs/{job['job_id']}").json()
    s = body["summary"]
    assert s["total"] == 4 and s["errors"] == 0 and s["needs_review"] == 0
    assert {x["regime"]: (x["count"], x["share"]) for x in s["by_regime"]} == {
        "ban": (0, 0), "restriction": (4, 1), "advantage": (0, 0), "none": (0, 0)}
    assert [x["idx"] for x in s["lowest_confidence"]] == [1, 2, 3, 4]
    x = client.get(f"/api/jobs/{job['job_id']}/export.xlsx")
    assert x.status_code == 200 and _sheets(x) == ["Сводка", "Результаты"]
    d = client.get(f"/api/jobs/{job['job_id']}/report.docx")
    assert d.status_code == 200 and d.headers["content-type"].startswith("application/vnd.openxmlformats") and _is_docx(d)
    assert 'filename="pp1875_report.docx"' in d.headers["content-disposition"]


def test_reports_wait_for_job_to_finish(client, fake_pipeline, monkeypatch):
    monkeypatch.setattr("app.api.classify.classify_job.delay", lambda job_id: None)  # задача остаётся в очереди
    job = client.post("/api/classify/batch", json={"names": ["ноутбук"]}).json()
    assert client.get(f"/api/jobs/{job['job_id']}").json()["summary"] is None
    for path in ("export.xlsx", "report.docx"):
        r = client.get(f"/api/jobs/{job['job_id']}/{path}")
        assert r.status_code == 409 and "ещё выполняется" in r.json()["detail"]


def test_justification_docx_for_single_item(client, fake_pipeline):
    r = client.post("/api/classify/justification.docx", json={"name": "Ноутбук"})
    assert r.status_code == 200 and _is_docx(r)
    assert 'filename="pp1875_obosnovanie.docx"' in r.headers["content-disposition"]


def test_reports_without_job(client, fake_pipeline):
    x = client.post("/api/report.xlsx", json={"names": ["Ноутбук", " ", "Монитор"]})
    assert x.status_code == 200 and _sheets(x) == ["Сводка", "Результаты"]
    assert fake_pipeline.calls[-1][0] == ["Ноутбук", "Монитор"]
    d = client.post("/api/report.docx", json={"names": ["Ноутбук"]})
    assert d.status_code == 200 and _is_docx(d)
    assert client.post("/api/report.xlsx", json={"names": ["x"] * 101}).status_code == 422
    assert client.post("/api/report.docx", json={"names": []}).status_code == 422


def test_reports_while_models_load_return_503(client, fake_pipeline, monkeypatch):
    from types import SimpleNamespace

    # подменяем сам объект состояния: настоящий флаг может поднять фоновая загрузка моделей приложения
    monkeypatch.setattr("app.api.classify.state", SimpleNamespace(models_ready=False))
    for path, body in (("/api/report.xlsx", {"names": ["Ноутбук"]}), ("/api/report.docx", {"names": ["Ноутбук"]}),
                       ("/api/classify/justification.docx", {"name": "Ноутбук"})):
        r = client.post(path, json=body)
        assert r.status_code == 503 and "запускается" in r.json()["detail"], path
