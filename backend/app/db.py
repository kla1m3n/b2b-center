from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401  регистрирует таблицы

    with engine.begin() as conn:
        # api и worker стартуют одновременно: без блокировки CREATE EXTENSION падает на гонке
        conn.execute(text("SELECT pg_advisory_xact_lock(18750)"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Сменили модель эмбеддингов → другая размерность: векторы и кэш пересоздаются (seed заполнит заново).
        dim = conn.execute(text(
            "SELECT atttypmod FROM pg_attribute WHERE attrelid = to_regclass('okpd2_text') AND attname = 'embedding'"
        )).scalar()
        if dim is not None and dim != get_settings().embed_dim:
            conn.execute(text("DROP TABLE okpd2_text"))
            conn.execute(text("DROP TABLE IF EXISTS classification_cache"))
        Base.metadata.create_all(conn)


def db_alive() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
