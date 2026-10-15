from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/pp1875"
    redis_url: str = "redis://localhost:6379/0"
    data_dir: str = "/data"
    upload_dir: str = "/uploads"  # загруженные редакции ПП (общий том api и worker)

    embed_model: str = "intfloat/multilingual-e5-large"
    embed_dim: int = 1024
    device: str = "cpu"
    retrieve_k: int = 20
    # Калибровка уверенности (w_score, w_margin, bias) — подбирается: python scripts/eval.py --fit-confidence
    confidence_coef: tuple[float, float, float] = (74.672, 3.317, -65.484)

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    needs_review_threshold: float = 0.60
    batch_limit: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
