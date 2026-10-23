# Классификатор товаров по ПП № 1875 — «Дрын Тим»

Кейс-чемпионат B2B-Center «AI Procurement Copilot», **задача 2**.
Пользователь вводит наименование товара (или список до 100) → система определяет код ОКПД2,
режим по ПП РФ № 1875 (запрет / ограничение / преимущество / не подпадает), пункт постановления и уверенность модели.

> Статус: в разработке. Готовы данные, БД, сверка с ПП, ИИ-конвейер, API и сайт. Дальше — документация, видео.

## Запуск

Нужен Docker Desktop.

```bash
docker-compose up --build
```

Первая сборка долгая (качаются модели ИИ, несколько ГБ). После старта:
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

### Дообученная модель поиска и ONNX

По умолчанию поиск по смыслу работает на `intfloat/multilingual-e5-large`. Дообученная на закупках версия (ноутбук
Kaggle, архив `artifacts.zip`) подключается настройками в `.env` — код менять не нужно:

| Вариант | Что положить в `data/` | `.env` |
|---|---|---|
| PyTorch | `models/e5-large-pp1875/` | `EMBED_MODEL=/data/models/e5-large-pp1875` |
| ONNX int8 (запрос в ~4 раза быстрее на CPU) | `models/e5-large-pp1875-onnx/` | `EMBED_MODEL=/data/models/e5-large-pp1875-onnx`<br>`EMBED_BACKEND=onnx` |

Для маленькой модели `rubert-mini-frida-pp1875` ещё `EMBED_DIM=312`. Папка `data/models/` в git не попадает.

Из `artifacts.zip/backend_data/` (если ноутбук написал «doc2query в экспорт вошёл»):
- `okpd2_synonyms.csv` → `data/okpd2_synonyms.csv` — синонимы плюс формулировки заказчиков от LLM;
- `index/data-models-e5-large-pp1875.npz` → `data/index/` — готовые эмбеддинги индекса (иначе бэкенд считает
  их на CPU, для ~100 тыс. текстов это десятки минут). Для ONNX переименуйте в `data-models-e5-large-pp1875-onnx.npz`:
  имя файла = `EMBED_MODEL` в нижнем регистре, всё кроме букв и цифр заменено на `-`.

Затем перезагрузка текстов поиска, калибровка уверенности и замеры:

```bash
docker compose build
docker compose run --rm -v ./backend:/app api python -m app.seed --reindex
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/dev.csv --fit-confidence --out /reports/eval_dev_ft.md
#  → строку CONFIDENCE_COEF=[a, b, c] из вывода записать в .env
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/testset.csv --out /reports/eval_testset_ft.md
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/stress.csv --out /reports/eval_stress_ft.md
docker-compose up --build
```

Откат: удалить строки `EMBED_*` из `.env` и снова `app.seed --reindex`. Если папку модели сохранила более новая
версия sentence-transformers, чем в образе, бэкенд загрузит её через transformers напрямую (в логе будет
предупреждение) — результат тот же.

Тесты:

```bash
docker compose run --rm -v ./backend:/app api pytest -q
```

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
  "alternatives": [{"code": "17.23.12.110", "title": "Конверты, письма-секретки", "confidence": 0.1345}],
  "confidence": 0.9709,
  "needs_review": false,
  "npa_matches": [
    {"item_id": 1814, "regime": "ban", "appendix": 1, "item_no": "10", "title": "Бумага и картон",
     "matched_code": "17.12", "quota": null, "has_conditions": false, "note": "",
     "source_url": "https://docs.cntd.ru/document/1310667825"},
    {"item_id": 2442, "regime": "advantage", "appendix": 3, "item_no": "13", "title": "Бумага и картон",
     "matched_code": "17.12", "quota": 90, "has_conditions": false, "note": "",
     "source_url": "https://docs.cntd.ru/document/1310667825"}
  ],
  "verdict": "ban",
  "explanation": "Наиболее близкое наименование ОКПД2: «Бумага для печати» (совпадение по «бумага а4»). Вердикт по ПП № 1875: запрет.",
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
curl http://localhost:8080/api/npa/items/1814        # пункт ПП: приложение, номер, текст, коды ОКПД2, доля, ссылка

curl -X POST http://localhost:8080/api/npa/upload \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -F "file=@pp1875.json" \
  -F "title=ПП РФ № 1875 (ред. на …)" \
  -F "source_url=https://…"
# {"version_id":2} — разбор идёт в фоне; редакция станет активной, когда статус в /api/npa/versions будет ready.
# Битый файл → статус failed, действующая редакция не меняется. Формат файла — docs/npa-structure.md.
```

## Как это работает

1. **Нормализация** названия (убираем артикулы, «шт», раскрываем «мфу», «ноут»…).
2. **Поиск по смыслу**: модель эмбеддингов сравнивает товар с ~21 тыс. наименований ОКПД2 и синонимами (pgvector).
3. **Сверка с ПП 1875** обычным кодом, без ИИ: иерархия ОКПД2 по цифрам (`26.20.1` включает `26.20.11`).
4. **Ответ**: код, режим, пункты приложений, уверенность, альтернативы.

## Где что лежит

| Путь | Что |
|---|---|
| `docs/superpowers/specs/` | дизайн (что и зачем делаем) |
| `docs/superpowers/plans/` | план реализации по задачам |
| `docs/npa-structure.md` | как устроено ПП 1875, источники данных |
| `data/okpd2.csv`, `data/npa/pp1875.json` | справочник ОКПД2 и ПП 1875 (ред. на 30.09.2026) |
| `data/okpd2_synonyms.csv` | бытовые названия для ходовых кодов |
| `data/eval/` | тестовые наборы: `dev.csv` — для настройки, `holdout.csv` — **не смотреть до финального замера** |
| `backend/app/classifier/` | ИИ-конвейер (`matcher.py` — сверка с законом) |
| `backend/app/api/` | REST API: классификация, пакеты, Excel, база НПА |
| `frontend/` | сайт (React + Vite, nginx) — см. `frontend/README.md` |
| `backend/scripts/` | загрузка данных, индекс, оценка точности (`eval.py`), замер скорости (`bench.py`) |
| `reports/` | результаты замеров |

## Как помогать команде

- **Датасет**: больше реальных позиций из zakupki.gov.ru → `data/eval/zakupki_raw.csv` (формат тот же), затем
  `python backend/scripts/prepare_testset.py --data data`.
- **Ошибки**: нашли неверную классификацию — заведите Issue на GitHub: товар, что выдала система, что правильно.
- **Сверка ПП**: проверить 10 позиций ПП 1875 по ГАРАНТ/Консультанту (см. `docs/npa-structure.md`).
