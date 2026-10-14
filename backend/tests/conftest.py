import os

import psycopg
import pytest

TEST_DB = "pp1875_test"
_base_url = os.environ["DATABASE_URL"]
_admin_dsn = _base_url.replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(_admin_dsn, autocommit=True) as _conn:
    if not _conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone():
        _conn.execute(f'CREATE DATABASE "{TEST_DB}"')
os.environ["DATABASE_URL"] = _base_url.rsplit("/", 1)[0] + "/" + TEST_DB

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    init_db()


@pytest.fixture
def session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
