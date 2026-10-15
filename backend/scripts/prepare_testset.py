"""Готовит тестовый набор из таблицы команды (позиции реальных закупок с zakupki.gov.ru).

Вход:  data/eval/zakupki_raw.csv  (Наименование;Код ОКПД2;Ссылка;Сфера)
Выход: data/eval/dev.csv      — половина для настройки (синонимы, параметры);
       data/eval/holdout.csv  — отложенная половина: смотрим только на итоговый замер.

Вердикт и пункты ПП считаются из эталонного кода детерминированно (по data/npa/pp1875.json).
Деление стратифицировано по сфере, с фиксированным seed — повторный запуск даёт то же разбиение.
"""
import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

REGIME = {1: "ban", 2: "restriction", 3: "advantage"}
FIELDS = ["name", "okpd2_expected", "regime_expected", "appendix_item_expected", "sphere", "source"]


def digits(code: str) -> str:
    return code.replace(".", "")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("/data"))
    p.add_argument("--seed", type=int, default=1875)
    a = p.parse_args()
    ev = a.data / "eval"
    items = json.loads((a.data / "npa" / "pp1875.json").read_text(encoding="utf-8"))["items"]
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
            ms = sorted((i for i in items if any(digits(code).startswith(digits(c)) for c in i["codes"])),
                        key=lambda i: (i["appendix"], i["item_no"]))
            rows.append({
                "name": name, "okpd2_expected": code,
                "regime_expected": REGIME[min(i["appendix"] for i in ms)] if ms else "none",
                "appendix_item_expected": " ".join(f"{i['appendix']}:{i['item_no']}" for i in ms),
                "sphere": sphere, "source": url,
            })

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
