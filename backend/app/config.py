from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/pp1875"
    redis_url: str = "redis://localhost:6379/0"
    data_dir: str = "/data"

    embed_model: str = "intfloat/multilingual-e5-base"
    embed_dim: int = 768
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    device: str = "cpu"
    retrieve_k: int = 20
    rerank_k: int = 10
    confidence_temperature: float = 1.0

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    needs_review_threshold: float = 0.60
    batch_limit: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
