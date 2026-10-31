"""Готовит тестовый набор из таблицы команды (позиции реальных закупок с zakupki.gov.ru).

Вход:  data/eval/zakupki_raw.csv  (Наименование;Код ОКПД2;Ссылка;Сфера)
Выход: data/eval/dev.csv      — половина для настройки (синонимы, параметры);
       data/eval/holdout.csv  — отложенная половина: смотрим только на итоговый замер.

Вердикт и пункты ПП считаются из эталонного кода тем же matcher, что в сервисе (по data/npa/pp1875.json).
Деление стратифицировано по сфере, с фиксированным seed.

Только для первичной сборки: при новых строках в zakupki_raw.csv повторное деление перемешало бы holdout
(часть отложенных позиций попала бы в dev). Пополнять наборы — scripts/add_eval_rows.py; без --force скрипт
не перезапишет существующие dev.csv/holdout.csv.
"""
import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from add_eval_rows import FIELDS, labeled  # noqa: E402
from app.npa.parser import parse_npa  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("/data"))
    p.add_argument("--seed", type=int, default=1875)
    p.add_argument("--force", action="store_true", help="пересоздать dev.csv и holdout.csv (holdout перемешается)")
    a = p.parse_args()
    ev = a.data / "eval"
    if not a.force and ((ev / "dev.csv").exists() or (ev / "holdout.csv").exists()):
        sys.exit("dev.csv/holdout.csv уже есть: пересоздание перемешает holdout. Пополнение — scripts/add_eval_rows.py; "
                 "пересоздать всё равно — --force")
    items = parse_npa(a.data / "npa" / "pp1875.json").items
    with (a.data / "okpd2.csv").open(encoding="utf-8") as f:
        known = {r["code"] for r in csv.DictReader(f, delimiter=";")}

    rows, skipped = [], []
    with (ev / "zakupki_raw.csv").open(encoding="utf-8-sig") as f:
        for r in csv.reader(f, delimiter=";"):
            if len(r) < 4 or not r[0].strip() or r[0].startswith("Наименование"):
                continue
            name, code, url, sphere = (x.strip() for x in r[:4])
            if code not in known:
                skipped.append((name, code))
                continue
            rows.append(labeled(name, code, sphere, url, items))

    by_sphere = defaultdict(list)
    for r in rows:
        by_sphere[r["sphere"]].append(r)
    rng = random.Random(a.seed)
    dev, holdout = [], []
    for sphere in sorted(by_sphere):
        group = by_sphere[sphere]
        rng.shuffle(group)
        half = len(group) // 2
        dev += group[:half]
        holdout += group[half:]

    for name, part in (("dev.csv", dev), ("holdout.csv", holdout)):
        with (ev / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";")
            w.writeheader()
            w.writerows(part)
    print(f"Позиций: {len(rows)} → dev {len(dev)}, holdout {len(holdout)}; пропущено (код не найден в ОКПД2): {len(skipped)}")
    for s in skipped:
        print("  пропущено:", *s)


if __name__ == "__main__":
    main()
