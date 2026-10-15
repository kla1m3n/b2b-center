from sqlalchemy import text

from app.config import get_settings
from app.db import engine, init_db


def embedding_dim() -> int:
    with engine.connect() as c:
        return c.execute(text(
            "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'okpd2_text'::regclass AND attname = 'embedding'"
        )).scalar_one()


def test_init_db_recreates_vectors_when_model_dimension_changes():
    with engine.begin() as c:
        c.execute(text("DELETE FROM okpd2_text"))
        c.execute(text("ALTER TABLE okpd2_text ALTER COLUMN embedding TYPE vector(3)"))
    assert embedding_dim() == 3
    init_db()
    assert embedding_dim() == get_settings().embed_dim
