# Для разработчиков

## Тесты

```bash
docker compose run --rm -v ./backend:/app api pytest -q     # backend
cd frontend && npm test                                      # сайт (vitest)
```

## Скрипты `backend/scripts/`

Запуск — в контейнере: `docker compose run --rm -v ./backend:/app [-v ./data:/datarw] [-v ./reports:/reports] api python scripts/<скрипт>.py …`.
Подробности и все параметры — в docstring каждого скрипта.

| Скрипт | Что делает |
|---|---|
| `import_open_data.py` | конвертирует открытые выгрузки ОКПД2 и ПП 1875 (github.com/prog815) в `data/okpd2.csv` и формат проекта |
| `build_npa_json.py` | собирает `data/npa/pp1875.json` из сверенной таблицы `data/npa/pp1875.csv` на дату `--date`: исключённые позиции убирает, ещё не действующие подпункты не включает |
| `synonyms_seed.py` → `gen_synonyms.py` | бытовые названия для ходовых кодов → `data/okpd2_synonyms.csv` (коды сверяются со справочником) |
| `download_models.py` | кладёт модель в образ при сборке (из `.hf` или с Hugging Face) |
| `build_index.py` | предрассчитывает эмбеддинги в `data/index/<model>.npz`, чтобы первый запуск был быстрым (см. [model.md](model.md)) |
| `prepare_testset.py` | делит `data/eval/zakupki_raw.csv` на `dev.csv` и `holdout.csv` |
| `make_stress_set.py` | стресс-набор `data/eval/stress.csv` из `testset.csv`: опечатки, артикулы, количество, шаблоны ЕИС |
| `relabel_npa_items.py` | пересчитывает эталонные пункты ПП в наборах оценки после смены базы НПА (`--write` — записать) |
| `eval.py` | точность на наборе → `reports/eval*.md`; `--fit-confidence` подбирает калибровку уверенности |
| `bench.py` | скорость: 1 товар p50/p95 и пакет из 100 → `reports/bench.md` |
| `compare_models.py` | сравнение моделей эмбеддингов по recall@k (индекс в памяти, БД не нужна) |

## Обновление базы ПП 1875

1. Внести изменения в `data/npa/pp1875.csv` (сверка — `docs/npa-structure.md`).
2. `python scripts/build_npa_json.py --csv /datarw/npa/pp1875.csv --out /datarw/npa/pp1875.json [--date ГГГГ-ММ-ДД]`.
3. На работающем сервисе — загрузить файл на странице «База НПА» (или `POST /api/npa/upload`), перезапуск не нужен.
4. `relabel_npa_items.py` по `dev.csv` и `testset.csv`, затем `eval.py` — проверить, что точность не упала.

> **01.01.2027** вступают в силу новые подпункты (82(1), 109(1)–(2), 110(1)–(3), 113(1)–(2) прил. 2, 44(1) прил. 3)
> и доля 50% по прил. 3 поз. 43 — пересобрать с `--date 2027-01-01` и загрузить как новую редакцию.

## Как помогать команде

- **Датасет**: больше реальных позиций из zakupki.gov.ru → `data/eval/zakupki_raw.csv` (формат тот же), затем
  `python backend/scripts/prepare_testset.py --data data`. `holdout.csv` не открывать до финального замера.
- **Ошибки**: нашли неверную классификацию — заведите Issue на GitHub: товар, что выдала система, что правильно.
- **Сверка ПП**: проверить 10 позиций ПП 1875 по ГАРАНТ/Консультанту (см. `docs/npa-structure.md`).
