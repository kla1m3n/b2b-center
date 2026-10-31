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

    # Модель эмбеддингов: имя на Hugging Face или папка. По умолчанию — e5-large, дообученная на закупках (Kaggle),
    # в ONNX int8 под AVX2 (onnx/model_quint8_avx2.onnx); при сборке качается только этот файл и токенизатор.
    # Префиксы запроса/документа выбираются по имени («e5», «frida»), поэтому имя модели должно их содержать.
    embed_model: str = "BOBUS2317/e5-large-pp1875-onnx"
    embed_dim: int = 1024  # 1024 у e5-large, 312 у rubert-mini-frida; при смене таблица векторов пересоздаётся
    # onnx (по умолчанию) — ONNX Runtime; torch — sentence-transformers (нужна модель с весами PyTorch,
    # например EMBED_MODEL=intfloat/multilingual-e5-large). embed_onnx_file — путь к .onnx внутри модели;
    # пусто — int8-файл под процессор, иначе onnx/model.onnx
    embed_backend: str = "onnx"
    embed_onnx_file: str = ""
    device: str = "cpu"
    retrieve_k: int = 20
    lexical_search: bool = True  # поиск по словам (BM25) вдобавок к поиску по смыслу, объединение по рангам
    spell_correction: bool = True  # исправлять опечатки по словарю наименований ОКПД2 и синонимов (spell.py)
    lexical_weight: float = 0.5  # вес поиска по словам в объединении (поиск по смыслу — 1.0)
    # Первым после объединения не ставится код, чьё сходство по смыслу ниже лучшего больше чем на этот зазор
    # (BM25 поднял его по совпавшему слову). 0 — выключено. 0,15 на 492 товарах (dev, testset, stress, validation):
    # +1 вердикт, ни один набор не хуже; 0,20–0,25 ничего не меняют, 0,10 теряет код
    lexical_max_gap: float = 0.15
    # Голосование по режиму ПП: вероятности кандидатов топ-vote_k (softmax сходства с температурой) суммируются
    # по режиму, побеждает режим с наибольшей суммой; код в ответе — лучший кандидат этого режима (pipeline._vote).
    # Выключено: на 492 товарах dev +1, validation −2 (477 против 478)
    verdict_vote: bool = False
    vote_k: int = 10
    vote_temperature: float = 0.03
    # Ансамбль: сходство = (1 − ensemble_weight) · основная модель + ensemble_weight · ensemble_model (ensemble.py).
    # ensemble_model — папка ONNX-модели или имя на Hugging Face; пусто — выключено. Векторы второй модели —
    # data/index/<модель>-onnx.npz (как у seed), недостающие считаются при старте. Выключено: с исходной e5-large
    # (avx512_vnni) при весе 0,3/0,5/0,7 на 492 товарах те же 479 (dev +1, validation −1), код top-1 на dev
    # 64,8/63,6/60,2% против 64,8%; уверенность откалибрована на сходстве одной модели, а память и время — вдвое
    ensemble_model: str = ""
    ensemble_weight: float = 0.5
    # Уверенность = вероятность верного вердикта по ПП (w_score, w_margin, bias); подбор: scripts/eval.py --fit-confidence.
    # Подобрана на dev под модель по умолчанию; у исходной e5-large было (11.055, 58.809, -8.864).
    confidence_coef: tuple[float, float, float] = (4.577, 0.429, -1.846)

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # «⚠ Проверьте вручную», если вероятность верного вердикта ниже порога. На dev (reports/eval_dev_ft_avx2.md):
    # уверенность 40–60% → вердикт верен в 29% случаев, 60–80% → в 85%, 80–100% → в 96%.
    needs_review_threshold: float = 0.80
    batch_limit: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
