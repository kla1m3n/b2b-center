# Классификатор товаров по ПП № 1875 — «Дрын Тим»

Кейс-чемпионат B2B-Center «AI Procurement Copilot», **задача 2**.
Пользователь вводит наименование товара (или список до 100) → система определяет код ОКПД2,
режим по ПП РФ № 1875 (запрет / ограничение / преимущество / не подпадает), пункт постановления и уверенность модели.

**Сайт:** [drunteam.ru](https://drunteam.ru)  
**Видео (4:57):** [video/drynteam_demo.mp4](video/drynteam_demo.mp4) — команда, техническое решение и работа сайта.

> Статус: готовы данные, БД, сверка с ПП (ред. на 30.09.2026), ИИ-конвейер с дообученной моделью поиска, API, сайт и видео.
> Дальше — финальный замер на `holdout`.

## Запуск

Нужен Docker Desktop.

```bash
docker-compose up --build
```

Первая сборка — 5–10 минут: качаются зависимости и модель поиска с Hugging Face (~560 МБ). После старта:
- **сайт: http://localhost:8080** (пока модели грузятся — баннер «Система запускается», ~1 мин)
- проверка готовности: http://localhost:8000/api/health (ждать `"status": "ok"`)
- документация API: http://localhost:8000/docs (порт 8000 открыт только на этом компьютере)

### Пароль на загрузку редакций ПП

Новая редакция ПП 1875 загружается на странице «База НПА» и меняет базу для всех пользователей.
На публичном сервере задайте пароль в `.env` в корне репозитория — тогда на сайте появится поле пароля:

```
ADMIN_TOKEN=change-me-to-a-long-random-password
```

Пароль — **латиницей** (буквы, цифры, знаки): он передаётся в HTTP-заголовке, кириллицу браузер отправить не может.
Без `ADMIN_TOKEN` загрузка открыта (удобно для локальной проверки).

### Тесты

```bash
docker compose run --rm -v ./backend:/app api pytest -q     # 88 тестов, ~2–3 мин
```

## Модель поиска

По умолчанию поиск по смыслу работает на
**[`BOBUS2317/e5-large-pp1875-onnx`](https://huggingface.co/BOBUS2317/e5-large-pp1875-onnx)** — это
`intfloat/multilingual-e5-large`, **дообученная на наименованиях из госзакупок** (пары «наименование → код ОКПД2»:
КТРУ, синонимы, наименования кодов, синтетика LLM), в **ONNX Runtime, int8 под AVX2**.

- **Без GPU и без настройки.** `docker-compose up --build` скачивает с Hugging Face только файл
  `onnx/model_quint8_avx2.onnx` и токенизатор (~560 МБ вместо 2,2 ГБ весов PyTorch). Квантование AVX2 работает на
  любом современном x86-процессоре.
- **Готовый индекс** — `data/index/bobus2317-e5-large-pp1875-onnx.npz` (16 065 текстов: наименования кодов нижнего
  уровня и синонимы). Первый запуск не считает эмбеддинги на CPU.
- **Калибровка уверенности** подобрана под эту модель на `dev` (`confidence_coef` в `backend/app/config.py`).

### Точность и скорость

Замер `scripts/eval.py` на CPU, отчёты — `reports/eval_*_ft_avx2.md`. Для сравнения — исходная e5-large в том же
конвейере (`reports/eval_*_onnx.md`).

| Набор | Вердикт по ПП 1875 | Код ОКПД2 top-1 | Исходная e5-large: вердикт / код |
|---|---|---|---|
| `dev` — 88 реальных закупок | **87,5%** | **63,6%** | 90,9% / 54,5% |
| `testset` — 32 чистых наименования | **100%** | **96,9%** | 100% / 100% |
| `stress` — 192 искажения (опечатки, артикулы, шаблоны ЕИС) | **100%** | **96,9%** | 100% / 99,0% |

- Дообученная модель заметно точнее находит **код** (dev: +9 пунктов top-1, +8 top-3). Вердикт на dev ниже на 3 товара:
  в большинстве этих случаев исходная модель угадывала вердикт с неверным кодом (медизделия, где заказчики сами ставят
  разные коды на похожие товары).
- Уверенность честная: при 80–100% вердикт верен в 96% случаев (dev), ниже 80% — пометка «Проверьте вручную».
- Скорость через API: **1 товар — ~0,23 с** (медиана), **100 товаров — ~15 с**. Требования ТЗ: < 5 с и < 2 мин.

### Другая модель

Модель меняется настройками в `.env` в корне репозитория — код менять не нужно:

| Вариант | `.env` |
|---|---|
| По умолчанию — дообученная, ONNX int8 | — |
| Исходная e5-large, ONNX int8 (официальный файл intfloat) | `EMBED_MODEL=intfloat/multilingual-e5-large`<br>`CONFIDENCE_COEF=[11.055, 58.809, -8.864]` |
| Исходная e5-large на PyTorch | `EMBED_MODEL=intfloat/multilingual-e5-large`<br>`EMBED_BACKEND=torch`<br>`CONFIDENCE_COEF=[11.055, 58.809, -8.864]` |
| Своя модель из папки `data/models/<имя>/` (в git не попадает) | `EMBED_MODEL=/data/models/<имя>`<br>`EMBED_BACKEND=onnx` или `torch` |
| Своя модель на Hugging Face | `EMBED_MODEL=<логин>/<имя>`<br>`EMBED_BACKEND=onnx` |

- Имя модели должно содержать `e5` или `frida`: по нему выбираются префиксы запроса и документа. Для
  `rubert-mini-frida` ещё `EMBED_DIM=312`.
- **ONNX:** в модели нужен файл `onnx/*.onnx`. Если int8-файлов несколько (`…_avx2`, `…_avx512_vnni`, `…_arm64`),
  берётся подходящий процессору; конкретный — `EMBED_ONNX_FILE=onnx/<файл>.onnx`. Пулинг читается из
  `1_Pooling/config.json` в форматах sentence-transformers 3.x и 5.x.
- **Индекс:** `data/index/<EMBED_MODEL в нижнем регистре, не буквы и не цифры → «-»>.npz`, у ONNX в конце `-onnx`.
  Если файла нет, бэкенд посчитает эмбеддинги при первом запуске (~15–20 мин на CPU).

Подключить новую модель (после правки `.env`):

```bash
docker compose build                                         # скачает модель с Hugging Face
docker compose up -d db redis
docker compose run --rm -v ./backend:/app -v ./data:/datarw api python scripts/build_index.py --data /datarw
docker compose run --rm -v ./backend:/app api python -m app.seed --reindex
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/dev.csv --fit-confidence --out /reports/eval_dev_new.md
#  → строку CONFIDENCE_COEF=[a, b, c] из вывода записать в .env
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/testset.csv --out /reports/eval_testset_new.md
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/stress.csv --out /reports/eval_stress_new.md
docker-compose up --build
```

Откат — удалить строки `EMBED_*` и `CONFIDENCE_COEF` из `.env`, `docker compose build` и снова `app.seed --reindex`.

Модель обучается ноутбуком в Kaggle — `training/kaggle/pp1875_kaggle.ipynb` (инструкция `training/kaggle/README.md`).
Экспорт — `artifacts.zip` **только с ONNX int8 под AVX2** (`<модель>-onnx/onnx/model_quint8_avx2.onnx`), готовым
индексом `backend_data/index/<имя>.npz` (имя уже как у `seed.index_name`) и, по желанию, выгрузкой на Hugging Face.
Формулировки doc2query ноутбук кладёт в `backend_data/okpd2_synonyms.csv`, только если с ними вердикт не хуже и на dev,
и на тестовом наборе; если в выводе «doc2query в экспорт не вошёл» — `data/okpd2_synonyms.csv` не заменять.

## API — примеры запросов

Базовый адрес — сайт `http://localhost:8080` (через nginx, как у пользователей) или `http://localhost:8000` (API напрямую).
Все запросы можно попробовать без командной строки в Swagger: http://localhost:8000/docs.

> Windows: используйте `curl.exe` и передавайте JSON с кириллицей из файла в UTF-8 (`--data-binary @query.json`) —
> иначе консоль может отправить текст не в UTF-8, и API ответит «There was an error parsing the body».

**Готовность сервиса**

```bash
curl http://localhost:8080/api/health
# {"status":"ok","db":true,"models":true,"npa_version":"ПП РФ № 1875 от 23.12.2024 (ред. на 30 сентября 2026 года)","npa_upload_protected":false}
```

**Один товар** (синхронно, обычно < 0,5 с; пока модели загружаются — `503`)

```bash
curl -X POST http://localhost:8080/api/classify \
  -H "Content-Type: application/json" \
  -d '{"name": "Бумага офисная А4"}'
```

Ответ (сокращён):

```json
{
  "input": "Бумага офисная А4",
  "okpd2": {"code": "17.12.14.110", "title": "Бумага для печати"},
  "alternatives": [{"code": "17.12.14.119", "title": "Бумага для печати прочая", "confidence": 0.7942}],
  "confidence": 0.8933,
  "needs_review": false,
  "npa_matches": [
    {"item_id": 10, "regime": "ban", "appendix": 1, "item_no": "10", "title": "Бумага и картон",
     "matched_code": "17.12", "quota": null, "has_conditions": false, "note": "",
     "source_url": "https://docs.cntd.ru/document/1310667825"},
    {"item_id": 663, "regime": "advantage", "appendix": 3, "item_no": "13", "title": "Бумага и картон",
     "matched_code": "17.12", "quota": 90, "has_conditions": false, "note": "",
     "source_url": "https://docs.cntd.ru/document/1310667825"}
  ],
  "verdict": "ban",
  "explanation": "Наиболее близкое наименование ОКПД2: «Бумага для печати» (совпадение по «бумага офисная»). Вердикт по ПП № 1875: запрет.",
  "error": null,
  "npa_source_url": "https://docs.cntd.ru/document/1310667825"
}
```

- `confidence` — вероятность верного вердикта (0…1); `needs_review: true`, если она ниже 0,8.
- `verdict`: `ban` (запрет, прил. 1), `restriction` (ограничение, прил. 2), `advantage` (прил. 3), `none` (не входит в приложения).
- `npa_matches` — все пункты ПП с текстом и ссылкой; `item_id` — для `GET /api/npa/items/{id}`.
- `npa_source_url` — текст действующей редакции ПП; есть у любого результата, в том числе `none`.

**Список до 100 товаров** — JSON или файл `.xlsx` / `.csv` / `.txt` (обработка в очереди, ответ `202`)

```bash
curl -X POST http://localhost:8080/api/classify/batch \
  -H "Content-Type: application/json" \
  -d '{"names": ["Ноутбук Lenovo IdeaPad 15", "Щебень гранитный", "Хлеб пшеничный"]}'
# {"job_id":"8f0c…"}

curl -X POST http://localhost:8080/api/classify/batch -F "file=@spec.xlsx"
```

Больше 100 товаров → `422 «Не более 100 товаров за один запрос»`. В файле можно оставить шапку, номера и количество —
колонка с наименованиями находится автоматически.

**Статус и результаты пакета, выгрузка в Excel**

```bash
curl http://localhost:8080/api/jobs/8f0c…
# {"job_id":"8f0c…","status":"running","total":3,"done":2,"error":null,"results":null}
# status: queued → running → done (results — массив, как у /api/classify) или failed (причина в error)

curl -o results.xlsx http://localhost:8080/api/jobs/8f0c…/export.xlsx   # после status = done
```

**База НПА: редакции, пункт, загрузка новой редакции без перезапуска**

```bash
curl http://localhost:8080/api/npa/versions          # редакции, новые сверху: статус, число позиций, предупреждения
curl http://localhost:8080/api/npa/items/10          # пункт ПП: приложение, номер, текст, коды ОКПД2, доля, ссылка

curl -X POST http://localhost:8080/api/npa/upload \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -F "file=@pp1875.json" \
  -F "title=ПП РФ № 1875 (ред. на …)" \
  -F "source_url=https://…"
# {"version_id":2} — разбор идёт в фоне; редакция станет активной, когда статус в /api/npa/versions будет ready.
# Битый файл → статус failed, действующая редакция не меняется. Формат файла — docs/npa-structure.md.
```

## Как это работает

1. **Нормализация** названия: убираем артикулы, количество, шаблоны ЕИС («Поставка товара:», «(или эквивалент)»),
   раскрываем сокращения («мфу», «ноут», «ДСП»), пометку «является медицинским изделием» переносим в начало как
   подсказку о сфере.
2. **Исправление опечаток** по словарю наименований ОКПД2 и синонимов («Телвеизор» → «телевизор», «пилта» → «плита»).
3. **Поиск кода ОКПД2** среди 15 432 кодов нижнего уровня и 633 синонимов:
   - по смыслу — дообученная модель эмбеддингов (ONNX int8) в pgvector;
   - по словам — BM25 с русским стеммингом;
   - объединение двух списков по рангам (RRF); при равной оценке выше код, чьё официальное наименование ближе к
     запросу, — ответ не зависит от порядка строк в БД.
4. **Правила поверх поиска**: товары выше услуг, если в наименовании нет признаков услуги; для медизделий — сначала
   медицинские разделы ОКПД2.
5. **Сверка с ПП 1875** обычным кодом, без ИИ: иерархия ОКПД2 по цифрам (`26.20.1` включает `26.20.11`, категория
   `XX.XX.XX.XX0` — свои подкатегории), исключения, подпункты вида `122(1)`.
6. **Ответ**: код, режим, пункты приложений со ссылкой на текст ПП, калиброванная уверенность, альтернативы.

## Где что лежит

| Путь | Что |
|---|---|
| `docs/superpowers/specs/` | дизайн (что и зачем делаем) |
| `docs/superpowers/plans/` | план реализации по задачам |
| `docs/npa-structure.md` | как устроено ПП 1875, источники данных |
| `data/okpd2.csv` | справочник ОКПД2 (21 081 код) |
| `data/npa/pp1875.csv`, `data/npa/pp1875.json` | ПП 1875, ред. на 30.09.2026: сверенная таблица и база для бэкенда (`scripts/build_npa_json.py`) |
| `data/okpd2_synonyms.csv` | бытовые названия для ходовых кодов |
| `data/index/` | готовые эмбеддинги текстов поиска для моделей (`*.npz`) |
| `data/eval/` | тестовые наборы: `dev.csv` — для настройки, `holdout.csv` — **не смотреть до финального замера** |
| `backend/app/classifier/` | ИИ-конвейер: `embedder.py` (модель, ONNX), `retriever.py` + `lexical.py` (поиск), `normalize.py`, `spell.py`, `rerank.py`, `matcher.py` (сверка с законом) |
| `backend/app/api/` | REST API: классификация, пакеты, Excel, база НПА |
| `frontend/` | сайт (React + Vite, nginx) — см. `frontend/README.md` |
| `backend/scripts/` | загрузка моделей (`download_models.py`), индекс (`build_index.py`), оценка точности (`eval.py`), пересчёт эталонных пунктов ПП (`relabel_npa_items.py`), замер скорости (`bench.py`) — все скрипты в `docs/contributing.md` |
| `reports/` | результаты замеров: `eval_*_ft_avx2.md` — модель по умолчанию; оглавление — `reports/README.md`, старые замеры — `reports/archive/` |
| `docs/contributing.md` | для разработчиков: скрипты, обновление базы ПП 1875 (в т.ч. к 01.01.2027) |

## Как помогать команде

- **Датасет**: больше реальных позиций из zakupki.gov.ru → `data/eval/zakupki_raw.csv` (формат тот же), затем
  `python backend/scripts/prepare_testset.py --data data`.
- **Ошибки**: нашли неверную классификацию — заведите Issue на GitHub: товар, что выдала система, что правильно.
- **Сверка ПП**: проверить 10 позиций ПП 1875 по ГАРАНТ/Консультанту (см. `docs/npa-structure.md`).
