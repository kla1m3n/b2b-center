# CLAUDE.md — b2b-center (классификатор по ПП РФ № 1875)

Кейс-чемпионат B2B-Center «AI Procurement Copilot», задача 2. Наименование товара → код ОКПД2 → режим по ПП 1875
(запрет / ограничение / преимущество / не подпадает), пункт ПП, уверенность. Документация для людей — `README.md`.

## Архитектура

- `backend/app/classifier/` — конвейер (`pipeline.py`): `normalize.py` → `retriever.py` (pgvector, top-K×`OVERFETCH`,
  свёртка по коду) + `lexical.py` (RRF) → `rerank.py` → `matcher.py` (сверка с ПП, **без ИИ**) → `confidence.py`.
- `embedder.py` — модель эмбеддингов: ONNX Runtime (по умолчанию) или torch. `prefixes()` выбирает префиксы
  **по имени модели**: `e5` → `query: `/`passage: `, `frida` → `search_query: `/`search_document: `. В имени модели
  (HF-репозиторий или папка) обязательно должно быть `e5` или `frida`.
- `pick_onnx_file` — выбор int8-файла под CPU: avx512_vnni → avx512 → avx2 (arm64 на ARM). Файлы по суффиксу:
  `onnx/model_quint8_avx2.onnx`, `model_qint8_avx512_vnni.onnx`, …
- `backend/app/seed.py` — загрузка ОКПД2, текстов поиска, ПП. Индекс `data/index/<index_name>.npz`:
  `model_slug(EMBED_MODEL)` (нижний регистр, не буквы/цифры → `-`) + `-onnx`, если backend=onnx и slug не кончается на
  `onnx`. Формат npz: `codes`, `texts`, `kinds` (str-массивы), `vectors` (float16); читается `allow_pickle=False`.
- `backend/app/api/` — FastAPI: `/api/classify`, `/api/classify/batch` (Celery, ≤100), `/api/jobs`, `/api/npa`.
- `backend/app/npa/` — редакции ПП; `data/npa/pp1875.json` (формат — `docs/npa-structure.md`).
- `frontend/` — React + Vite за nginx.
- `training/` — дообучение: `finetune.py` (короткий скрипт) и `kaggle/` (полный ноутбук, см. ниже).

## Настройки (`backend/app/config.py`, переопределяются `.env`)

`EMBED_MODEL` (по умолчанию `BOBUS2317/e5-large-pp1875-onnx`), `EMBED_BACKEND` (`onnx`), `EMBED_ONNX_FILE`,
`EMBED_DIM` (1024; frida — 312), `CONFIDENCE_COEF` (подбирается `eval.py --fit-confidence` под каждую модель),
`ADMIN_TOKEN` (латиница). Аргументы сборки `EMBED_*` прокинуты в `docker-compose.yml`; `scripts/download_models.py`
при сборке качает для ONNX только `onnx/*int8*.onnx` + токенизатор (в работающем контейнере интернета нет).

## Команды

```bash
docker-compose up --build                                                  # сайт :8080, API :8000
docker compose run --rm -v ./backend:/app api pytest -q                     # тесты
docker compose run --rm -v ./backend:/app api python -m app.seed --reindex  # после смены синонимов/индекса/модели
docker compose run --rm -v ./backend:/app -v ./data:/datarw api python scripts/build_index.py --data /datarw
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py \
    --testset /data/eval/dev.csv [--fit-confidence] --out /reports/eval_dev_X.md      # также testset.csv, stress.csv
```

## Правила

- **`data/eval/holdout.csv` не использовать** ни для обучения, ни для подбора параметров/выбора модели — только один
  финальный замер для отчёта. Выбор — по `dev.csv`, проверка — `testset.csv` и `stress.csv`.
- Правило иерархии ОКПД2 — только `matcher.code_covers`. Копии правила (`training/kaggle/kaggle_dataset/onnx_export.py`
  `covers`, `pp1875_core.match_prefix`) обязаны совпадать с ним: префикс цифр + коды с нулями в конце
  (`XX.XX.XX.XX0` — категория, `.X00`/`.000` — группа) покрывают коды своей группы. Меняешь одно — меняй все и тест
  `backend/tests/classifier/test_matcher.py`.
- Вердикт строится кодом по ПП, LLM в конвейере не решает режим.
- Смена модели эмбеддингов = новый индекс (`build_index.py` или npz из ноутбука) + `app.seed --reindex` +
  новый `CONFIDENCE_COEF` + отчёты `reports/eval_*`. Индекс прежней модели не удалять (откат).
- `data/models/`, `data/train/`, `.env`, `.hf/*` в git не попадают. Веса моделей в git не класть.
- Секреты — никогда в файлы, git, логи: `HF_TOKEN` только в Kaggle Secrets; ключ GigaChat — переменная
  `GIGACHAT_CREDENTIALS` или скрытый ввод; личный токен КТРУ — только локально.
- Тексты, комментарии, сообщения коммитов — по-русски, коротко, как в существующем коде.

## Обучение (`training/kaggle/`, инструкция — `training/kaggle/README.md`)

- `pp1875_kaggle.ipynb` + датасет Kaggle `pp1875-data` (`kaggle_dataset/*.py` + данные из `data/` и большие файлы
  `train_v2.csv`, `train_pairs.csv`, `okpd2_generated_raw.csv`, которых нет в git). Запуск — Save & Run All (Commit).
- e5-large, InfoNCE с трудными негативами (`V2_NEG_SHARE`), выбор эпохи: verdict + code@1 + 0,5·code@20 на dev;
  doc2query (формулировки GigaChat в индекс) остаётся, только если не хуже на dev **и** test.
- Экспорт **только ONNX**: `onnx_export.py` отдельным процессом → `<модель>-onnx/onnx/model_quint8_avx2.onnx`
  (одним файлом, без внешних данных), `backend_data/index/<index_name>.npz`, `backend_data/okpd2_synonyms.csv`,
  `metrics.json`; при `HF_REPO` папка ONNX выгружается на Hugging Face.
- `tools/gigachat_generate.py` — генерация текстов на своём ПК (возобновляемая); промпты/отбор кодов — в `pp1875_core.py`.
- Правя ноутбук, держи совместимость с бэкендом: имя файла ONNX, формула имени индекса (`index_name` в ячейке
  экспорта = `seed.index_name`), формат npz, префиксы по имени модели. Ноутбук должен идти от начала до конца
  (Run All): ячейки зависят от переменных предыдущих.
