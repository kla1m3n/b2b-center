from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/pp1875"
    redis_url: str = "redis://localhost:6379/0"
    data_dir: str = "/data"
    upload_dir: str = "/uploads"  # загруженные редакции ПП (общий том api и worker)
    # Пароль на загрузку новой редакции ПП (ADMIN_TOKEN в .env). Пусто — загрузка открыта (локальный запуск у жюри);
    # на публичном сервере обязательно задать, иначе любой посетитель сайта может подменить базу.
    # Только латиница, цифры и знаки: пароль идёт в HTTP-заголовке X-Admin-Token, кириллицу браузер не отправит.
    admin_token: str = ""

    embed_model: str = "intfloat/multilingual-e5-large"
    embed_dim: int = 1024
    device: str = "cpu"
    retrieve_k: int = 20
    # Уверенность = вероятность верного вердикта по ПП (w_score, w_margin, bias); подбор: scripts/eval.py --fit-confidence
    confidence_coef: tuple[float, float, float] = (11.055, 58.809, -8.864)

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # «⚠ Проверьте вручную», если вероятность верного вердикта ниже порога. На dev (reports/eval_dev.md):
    # уверенность 60–80% → вердикт верен в 69% случаев, 80–100% → в 92%. При старом пороге 0.60 пометка
    # после перекалибровки не срабатывала ни разу (минимальная уверенность на dev — около 60%).
    needs_review_threshold: float = 0.80
    batch_limit: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
