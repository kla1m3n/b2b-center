"""Строит data/okpd2_synonyms.csv (code;text) из scripts/synonyms_seed.py, сверяя коды со справочником.

Правило сопоставления записи (префикс, регулярка, синонимы):
  * регулярка пустая  → синонимы привязываются к самому коду-префиксу (он должен существовать);
  * иначе             → ко всем кодам нижнего уровня под префиксом, чьё наименование подходит (не более 3).

Запуск (на хосте или в контейнере): python scripts/gen_synonyms.py --data ../data
"""
import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from synonyms_seed import SEED  # noqa: E402

MAX_CODES_PER_ENTRY = 3


def resolve(rows: list[dict], prefix: str, pattern: str) -> list[str]:
    by_code = {r["code"]: r for r in rows}
    if not pattern:
        return [prefix] if prefix in by_code else []
    rx = re.compile(pattern, re.IGNORECASE)
    digits = prefix.replace(".", "")
    hits = [r["code"] for r in rows
            if r["is_leaf"] == "1" and r["code"].replace(".", "").startswith(digits) and rx.search(r["title"])]
    return hits[:MAX_CODES_PER_ENTRY]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("/data"))
    a = p.parse_args()
    with (a.data / "okpd2.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    out, unresolved = [], []
    for prefix, pattern, synonyms in SEED:
        codes = resolve(rows, prefix, pattern)
        if not codes:
            unresolved.append((prefix, pattern))
        out += [(c, s) for c in codes for s in synonyms]
    out = sorted(set(out))
    with (a.data / "okpd2_synonyms.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["code", "text"])
        w.writerows(out)
    print(f"Синонимов: {len(out)}, кодов: {len({c for c, _ in out})}, не сопоставлено записей: {len(unresolved)}")
    for u in unresolved:
        print("  не найдено:", *u)


if __name__ == "__main__":
    main()
