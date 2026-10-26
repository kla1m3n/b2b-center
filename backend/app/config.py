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

    # Модель эмбеддингов: имя на Hugging Face или папка (дообученная в Kaggle: /data/models/e5-large-pp1875).
    # Префиксы запроса/документа выбираются по имени («e5», «frida»), поэтому имя папки должно их содержать.
    embed_model: str = "intfloat/multilingual-e5-large"
    embed_dim: int = 1024  # 1024 у e5-large, 312 у rubert-mini-frida; при смене таблица векторов пересоздаётся
    # onnx (по умолчанию) — ONNX Runtime, int8-модель: у intfloat/multilingual-e5-large она есть в репозитории HF
    # (onnx/model_qint8_avx512_vnni.onnx), при сборке качается только она; torch — sentence-transformers.
    # embed_onnx_file — путь к .onnx внутри модели; пусто — int8-файл под процессор, иначе onnx/model.onnx
    embed_backend: str = "onnx"
    embed_onnx_file: str = ""
    device: str = "cpu"
    retrieve_k: int = 20
    lexical_search: bool = True  # поиск по словам (BM25) вдобавок к поиску по смыслу, объединение по рангам
    spell_correction: bool = True  # исправлять опечатки по словарю наименований ОКПД2 и синонимов (spell.py)
    lexical_weight: float = 0.5  # вес поиска по словам в объединении (поиск по смыслу — 1.0)
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
