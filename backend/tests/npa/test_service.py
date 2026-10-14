import shutil
from pathlib import Path

import pytest
from sqlalchemy import delete

from app.models import NpaItem, NpaVersion
from app.npa.service import create_version, get_active_items, get_active_version, process_version

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def clean_npa(session):
    session.execute(delete(NpaItem))
    session.execute(delete(NpaVersion))
    session.commit()
    yield
    session.execute(delete(NpaItem))
    session.execute(delete(NpaVersion))
    session.commit()


@pytest.fixture
def active_version(session, clean_npa, tmp_path):
    src = tmp_path / "sample.json"
    shutil.copy(FIXTURES / "npa_sample.json", src)
    v = create_version(session, src, "образец", "https://example.org")
    process_version(session, v.id)
    return session.get(NpaVersion, v.id)


def test_process_version_activates_and_stores_items(session, active_version):
    assert active_version.status == "ready"
    assert get_active_version(session).id == active_version.id
    items = get_active_items(session)
    assert len(items) == 6
    assert all(i.version_id == active_version.id for i in items)


def test_failed_version_keeps_previous_active(session, active_version, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    v = create_version(session, bad, "битая", "")
    process_version(session, v.id)
    failed = session.get(NpaVersion, v.id)
    session.refresh(failed)
    assert failed.status == "failed" and failed.error
    assert get_active_version(session).id == active_version.id


def test_new_version_replaces_active(session, active_version, tmp_path):
    src = tmp_path / "v2.json"
    shutil.copy(FIXTURES / "npa_sample.json", src)
    v2 = create_version(session, src, "вторая", "")
    process_version(session, v2.id)
    assert get_active_version(session).id == v2.id
    assert session.query(NpaVersion).filter_by(is_active=True).count() == 1
