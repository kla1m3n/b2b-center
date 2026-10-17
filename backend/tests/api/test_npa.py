from pathlib import Path

import pytest
from sqlalchemy import delete

from app.models import NpaItem, NpaVersion

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def celery_eager():
    from app.celery_app import celery

    celery.conf.task_always_eager = True
    yield
    celery.conf.task_always_eager = False


@pytest.fixture
def clean_npa(session, tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    session.execute(delete(NpaItem))
    session.execute(delete(NpaVersion))
    session.commit()
    yield
    session.execute(delete(NpaItem))
    session.execute(delete(NpaVersion))
    session.commit()
    get_settings.cache_clear()


def upload(client, name: str, data: bytes, title: str = "Редакция"):
    return client.post("/api/npa/upload", files={"file": (name, data, "application/json")},
                       data={"title": title, "source_url": "https://example.org/pp1875"})


def test_upload_new_edition_becomes_active(client, clean_npa, celery_eager):
    r = upload(client, "pp.json", (FIXTURES / "npa_sample.json").read_bytes(), "Редакция для теста")
    assert r.status_code == 202
    versions = client.get("/api/npa/versions").json()
    v = next(x for x in versions if x["id"] == r.json()["version_id"])
    assert v["status"] == "ready" and v["is_active"] and v["items_count"] == 6
    assert v["title"] == "Редакция для теста"
    health = client.get("/api/health").json()
    assert health["npa_version"] == "Редакция для теста"


def test_broken_upload_keeps_previous_edition(client, clean_npa, celery_eager):
    good = upload(client, "pp.json", (FIXTURES / "npa_sample.json").read_bytes()).json()["version_id"]
    bad = upload(client, "pp.json", b"not json").json()["version_id"]
    versions = {v["id"]: v for v in client.get("/api/npa/versions").json()}
    assert versions[bad]["status"] == "failed" and versions[bad]["error"]
    assert versions[good]["is_active"] and not versions[bad]["is_active"]


def test_upload_rejects_unknown_format(client, clean_npa):
    r = client.post("/api/npa/upload", files={"file": ("pp.pdf", b"%PDF", "application/pdf")}, data={"title": "x"})
    assert r.status_code == 422 and ".json" in r.json()["detail"]


def test_npa_item_text_for_reference_link(client, clean_npa, celery_eager, session):
    upload(client, "pp.json", (FIXTURES / "npa_sample.json").read_bytes())
    item = session.query(NpaItem).filter_by(appendix=2, item_no="195").one()
    r = client.get(f"/api/npa/items/{item.id}").json()
    assert r["appendix"] == 2 and r["item_no"] == "195" and "26.20.11" in r["codes"]
    assert r["regime"] == "restriction" and r["source_url"] == "https://example.org/pp1875"
    assert client.get("/api/npa/items/999999").status_code == 404


@pytest.fixture
def admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-1875")  # заголовки HTTP — только латиница
    from app.config import get_settings

    get_settings.cache_clear()
    yield "secret-1875"
    get_settings.cache_clear()


def test_upload_requires_admin_token_when_set(client, clean_npa, admin_token, celery_eager):
    sample = (FIXTURES / "npa_sample.json").read_bytes()
    assert upload(client, "pp.json", sample).status_code == 403
    wrong = client.post("/api/npa/upload", files={"file": ("pp.json", sample, "application/json")},
                        data={"title": "x"}, headers={"X-Admin-Token": "wrong-token"})
    assert wrong.status_code == 403 and "пароль" in wrong.json()["detail"]
    assert client.get("/api/npa/versions").json() == []  # отклонённая загрузка не создаёт редакцию
    ok = client.post("/api/npa/upload", files={"file": ("pp.json", sample, "application/json")},
                     data={"title": "x"}, headers={"X-Admin-Token": admin_token})
    assert ok.status_code == 202
    assert client.get("/api/health").json()["npa_upload_protected"] is True


def test_upload_open_without_admin_token(client, clean_npa):
    assert client.get("/api/health").json()["npa_upload_protected"] is False
