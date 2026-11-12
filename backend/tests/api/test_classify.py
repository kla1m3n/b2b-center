from io import BytesIO

import pytest
from openpyxl import Workbook

from app import state
from app.schemas import ClassificationResult, Okpd2Ref, Regime


class FakePipeline:
    """Подменяет ИИ-конвейер: API-тесты проверяют HTTP-слой, а не модель."""

    def __init__(self):
        self.calls = []
        self.code_calls = []

    def classify_many(self, names, npa_version_id=None):
        self.calls.append((list(names), npa_version_id))
        return [ClassificationResult(input=n, okpd2=Okpd2Ref(code="26.20.11.110", title="Ноутбуки"),
                                     confidence=0.9, needs_review=False, verdict=Regime.restriction) for n in names]

    def classify_with_codes(self, names, codes, npa_version_id=None):
        self.code_calls.append((list(names), list(codes)))
        out = []
        for r, code in zip(self.classify_many(names, npa_version_id), codes):
            if code == "99.99.99.999":
                raise ValueError(f"Код {code} не найден в справочнике ОКПД2")
            if code:
                r = r.model_copy(update={"okpd2": Okpd2Ref(code=code, title="Выбранный код"), "code_confirmed": True,
                                         "auto_code": "26.20.11.110", "verdict": Regime.none})
            out.append(r)
        return out


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


def test_classify_with_code_chosen_by_specialist(client, fake_pipeline):
    r = client.post("/api/classify", json={"name": "Ноутбук", "code": "26.20.11.130"})
    assert r.status_code == 200
    body = r.json()
    assert body["okpd2"]["code"] == "26.20.11.130" and body["code_confirmed"] is True and body["auto_code"] == "26.20.11.110"
    assert fake_pipeline.code_calls == [(["Ноутбук"], ["26.20.11.130"])]
    # без кода — обычная классификация
    assert client.post("/api/classify", json={"name": "Ноутбук"}).json()["code_confirmed"] is False
    assert len(fake_pipeline.code_calls) == 1


def test_classify_with_bad_or_unknown_code(client, fake_pipeline):
    assert client.post("/api/classify", json={"name": "Ноутбук", "code": "не код"}).status_code == 422
    r = client.post("/api/classify", json={"name": "Ноутбук", "code": "99.99.99.999"})
    assert r.status_code == 422 and "не найден в справочнике" in r.json()["detail"]


def test_reports_with_codes_chosen_by_specialist(client, fake_pipeline):
    body = {"names": ["Ноутбук", "  ", "Монитор"], "codes": [None, "10.71.11.110", "26.20.17.110"]}
    x = client.post("/api/report.xlsx", json=body)
    assert x.status_code == 200
    # пустое наименование отброшено вместе со своим кодом — коды остались у своих товаров
    assert fake_pipeline.code_calls[-1] == (["Ноутбук", "Монитор"], [None, "26.20.17.110"])
    from openpyxl import load_workbook

    ws = load_workbook(BytesIO(x.content))["Результаты"]
    assert ws["C3"].value == "26.20.17.110" and ws["H3"].value == "код подтверждён специалистом"
    assert client.post("/api/report.docx", json=body).status_code == 200
    assert client.post("/api/report.xlsx", json={"names": ["a", "b"], "codes": ["26.20"]}).status_code == 422
    d = client.post("/api/classify/justification.docx", json={"name": "Ноутбук", "code": "26.20.11.130"})
    assert d.status_code == 200 and _is_docx(d)


def test_annotated_xlsx_returns_users_table_with_results(client, fake_pipeline):
    from openpyxl import load_workbook

    wb = Workbook()
    for row in (["№", "Наименование", "Кол-во"], [1, "Ноутбук", 5], [2, "Монитор", 3]):
        wb.active.append(row)
    buf = BytesIO()
    wb.save(buf)
    files = {"file": ("spec.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = client.post("/api/report/annotated.xlsx", files=files, data={"codes": '[null, "26.20.17.110"]'})
    assert r.status_code == 200 and 'filename="pp1875_specification.xlsx"' in r.headers["content-disposition"]
    out = load_workbook(BytesIO(r.content))
    ws = out.active
    assert [c.value for c in ws[1]][:5] == ["№", "Наименование", "Кол-во", "Код ОКПД2", "Наименование ОКПД2"]
    assert [c.value for c in ws[2]][:4] == [1, "Ноутбук", 5, "26.20.11.110"]
    assert ws["D3"].value == "26.20.17.110" and ws["I3"].value == "код подтверждён специалистом"
    assert "Сводка ПП 1875" in out.sheetnames
    # без кодов — обычная классификация; неверные входные данные — 422 с понятным текстом
    assert client.post("/api/report/annotated.xlsx", files=files).status_code == 200
    bad = client.post("/api/report/annotated.xlsx", files={"file": ("spec.csv", b"a;b", "text/csv")})
    assert bad.status_code == 422 and "только в таблицу Excel" in bad.json()["detail"]
    assert client.post("/api/report/annotated.xlsx", files=files, data={"codes": "не json"}).status_code == 422
    assert client.post("/api/report/annotated.xlsx", data={"codes": "[]"}).status_code == 422
