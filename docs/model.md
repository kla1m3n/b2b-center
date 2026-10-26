# Модель поиска: варианты, ONNX, переиндексация

По умолчанию поиск по смыслу работает на **`BOBUS2317/e5-large-pp1875-onnx`** — `multilingual-e5-large`, дообученная
на закупках (ноутбук Kaggle), в **ONNX Runtime, int8 под AVX2** (`onnx/model_quint8_avx2.onnx`, любой современный x86).
При сборке с Hugging Face качается только этот файл и токенизатор (~560 МБ вместо 2,2 ГБ весов PyTorch), индекс к нему
лежит в `data/index/bobus2317-e5-large-pp1875-onnx.npz`, калибровка уверенности подобрана под неё
(`reports/eval_*_ft_avx2.md`, сравнение вариантов — `reports/README.md`).

## Другие варианты

Подключаются настройками в `.env` — код менять не нужно:

| Вариант | Что положить в `data/` | `.env` |
|---|---|---|
| Исходная e5-large, ONNX int8 (официальный файл) | ничего | `EMBED_MODEL=intfloat/multilingual-e5-large`<br>`CONFIDENCE_COEF=[11.055, 58.809, -8.864]` |
| Исходная e5-large на PyTorch | ничего | `EMBED_MODEL=intfloat/multilingual-e5-large`<br>`EMBED_BACKEND=torch`<br>`CONFIDENCE_COEF=[11.055, 58.809, -8.864]` |
| PyTorch | `models/e5-large-pp1875/` | `EMBED_MODEL=/data/models/e5-large-pp1875`<br>`EMBED_BACKEND=torch` |
| ONNX int8 (запрос в ~4 раза быстрее на CPU) | `models/e5-large-pp1875-onnx/` | `EMBED_MODEL=/data/models/e5-large-pp1875-onnx`<br>`EMBED_BACKEND=onnx` |
| ONNX int8 с Hugging Face (для сборки на чистой машине) | ничего | `EMBED_MODEL=<логин>/e5-large-pp1875-onnx`<br>`EMBED_BACKEND=onnx` |

Для маленькой модели `rubert-mini-frida-pp1875` ещё `EMBED_DIM=312`. Папка `data/models/` в git не попадает.

## ONNX с Hugging Face

`docker compose build` передаёт `EMBED_MODEL` и `EMBED_BACKEND` в сборку, и
`scripts/download_models.py` кладёт в образ только файл ONNX, токенизатор и конфиги (без весов PyTorch). В репозитории
на HF — содержимое папки `e5-large-pp1875-onnx/` из архива, файл модели в `onnx/`. Если там несколько int8-файлов
(`…_avx2`, `…_avx512_vnni`, `…_arm64`), бэкенд сам берёт подходящий процессору; конкретный задаётся
`EMBED_ONNX_FILE=onnx/<файл>.onnx`. Квантование под `avx512_vnni` работает и на процессорах без AVX-512, но медленнее —
для чужих машин надёжнее `avx2`.

## Артефакты из ноутбука Kaggle

Из `artifacts.zip/backend_data/` (если ноутбук написал «doc2query в экспорт вошёл»):
- `okpd2_synonyms.csv` → `data/okpd2_synonyms.csv` — синонимы плюс формулировки заказчиков от LLM;
- `index/data-models-e5-large-pp1875.npz` → `data/index/` — готовые эмбеддинги индекса (иначе бэкенд считает
  их на CPU, для ~100 тыс. текстов это десятки минут). Имя файла = `EMBED_MODEL` в нижнем регистре, всё кроме букв и
  цифр заменено на `-`; при `EMBED_BACKEND=onnx` в конце `-onnx` (если его ещё нет в имени).

Индекс для ONNX лучше построить той же int8-моделью (16 тыс. текстов — ~20 мин на CPU), тогда запрос и индекс
считаются одинаково:

```bash
docker compose run --rm -v ./backend:/app -v ./data:/datarw api python scripts/build_index.py --data /datarw --model <EMBED_MODEL>
```

## Переиндексация, калибровка уверенности, замеры

```bash
docker compose build
docker compose run --rm -v ./backend:/app api python -m app.seed --reindex
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/dev.csv --fit-confidence --out /reports/eval_dev_ft.md
#  → строку CONFIDENCE_COEF=[a, b, c] из вывода записать в .env
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/testset.csv --out /reports/eval_testset_ft.md
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/stress.csv --out /reports/eval_stress_ft.md
docker-compose up --build
```

Откат: удалить строки `EMBED_*` из `.env`, `docker compose build` и снова `app.seed --reindex`. Если папку модели сохранила более новая
версия sentence-transformers, чем в образе, бэкенд загрузит её через transformers напрямую (в логе будет
предупреждение) — результат тот же.
