# Дообучение модели поиска

Два способа, оба дают ONNX int8 под AVX2, который бэкенд подключает без правки кода:

- **`kaggle/`** — полный ноутбук (`pp1875_kaggle.ipynb`): выборка v2 с трудными негативами, doc2query от GigaChat,
  выбор эпохи по вердикту ПП на dev, экспорт **только в ONNX**, готовый индекс и `okpd2_synonyms.csv` для `data/`,
  опциональная выгрузка на Hugging Face. Инструкция — `kaggle/README.md`, раздел 7 — подключение к бэкенду.
- **`finetune.py`** — короткий скрипт ниже (MNRL на `make_train_set.py`).

Модель по умолчанию (`BOBUS2317/e5-large-pp1875-onnx`) обучена в Kaggle на КТРУ и синтетике LLM. Здесь — повторяемое
дообучение на расширенной выборке и подключение результата к сайту без правки кода.

## 1. Выборка (локально, ~1 мин)

```bash
docker run --rm -v ./backend:/app -v ./data:/data -v <папка с train_pairs.csv и synth.csv>:/extra:ro pp1875-backend \
  python scripts/make_train_set.py --extra /extra/train_pairs.csv /extra/synth.csv --out /data/train/train_full.csv
```

`train_pairs.csv` (КТРУ) и `synth.csv` (синтетика LLM) — из архива ноутбука обучения; без `--extra` в выборке только
наши данные (`scripts/make_train_set.py`: наименования кодов, синонимы, `train_seed.py`, искажения как в ЕИС).
Все строки, похожие на `data/eval/*.csv` (включая holdout), выбрасываются — замер после обучения честный.
`data/train/` в git не попадает: файл большой и пересобирается командой выше.

## 2. Обучение (Kaggle, GPU T4, ~1 ч)

1. Kaggle → *Datasets* → *New dataset*: `data/train/train_full.csv`, `data/okpd2.csv`, `data/okpd2_synonyms.csv`,
   `training/finetune.py`.
2. *New notebook* → *Add data* → этот датасет; *Settings* → *Accelerator* → **GPU T4 x1**, *Internet* — on.
3. Ячейки:

```python
!pip install -q -U "sentence-transformers[onnx]" datasets accelerate
!cp /kaggle/input/<датасет>/finetune.py .
!python finetune.py --train /kaggle/input/<датасет>/train_full.csv \
    --okpd2 /kaggle/input/<датасет>/okpd2.csv --synonyms /kaggle/input/<датасет>/okpd2_synonyms.csv \
    --out e5-large-pp1875-v2
```

Скрипт печатает точность поиска на проверочных кодах (их нет в обучении) до и после обучения, затем делает
ONNX int8 под AVX2 и архив `e5-large-pp1875-v2-onnx.zip` — скачать из *Output*. Пробный запуск на пару минут:
`--max-rows 2000`. Продолжить обучение модели друга вместо исходной e5-large: `--base <папка PyTorch-модели>`.

## 3. Подключение и замер (локально)

```bash
# распаковать архив в data/models/ → data/models/e5-large-pp1875-v2-onnx/onnx/model_quint8_avx2.onnx
# в .env:
#   EMBED_MODEL=/data/models/e5-large-pp1875-v2-onnx
#   EMBED_BACKEND=onnx
docker compose run --rm -v ./backend:/app -v ./data:/datarw api python scripts/build_index.py --data /datarw   # ~20 мин на CPU
docker compose run --rm -v ./backend:/app api python -m app.seed --reindex
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/dev.csv --fit-confidence --out /reports/eval_dev_v2.md
#  → строку CONFIDENCE_COEF=[a, b, c] из вывода записать в .env
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/testset.csv --out /reports/eval_testset_v2.md
docker compose run --rm -v ./backend:/app -v ./reports:/reports api python scripts/eval.py --testset /data/eval/stress.csv --out /reports/eval_stress_v2.md
```

Сравнить с `reports/eval_*_ft_avx2.md`. Учтите: в обучении текущей модели было 25 из 88 наименований `dev`
дословно (из КТРУ), в новой выборке их нет — dev у новой модели честнее, сравнивать лучше и по testset/stress.
Если новая модель лучше — выложить папку на Hugging Face и сделать её моделью по умолчанию
(`embed_model` и `confidence_coef` в `backend/app/config.py`, индекс `data/index/<имя>.npz`).
Откат — удалить строки `EMBED_*` и `CONFIDENCE_COEF` из `.env` и снова `app.seed --reindex`.
