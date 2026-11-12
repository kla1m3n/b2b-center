"""Справочник «наименование позиции КТРУ → код ОКПД2» для точного поиска (app/classifier/ktru.py).

Источник — снимок каталога КТРУ (references/ktru.csv из пакета okpd2_ktru_ready: колонки text, ktru_code; код ОКПД2 —
часть ktru_code до дефиса). В справочник идут только наименования с одним кодом ОКПД2 нижнего уровня: если одно
название встречается в КТРУ с разными кодами, точного ответа нет — решает поиск.

    python scripts/build_ktru_names.py --ktru <references/ktru.csv> --okpd2 /data/okpd2.csv --out /data/ktru_names.csv
"""
import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.classifier.normalize import normalize  # noqa: E402

KTRU_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{2}\.\d{3})-\d+$")


def build(ktru_rows, leaf: set[str]) -> tuple[list[tuple[str, str]], int]:
    """[(код, наименование)] по одному на нормализованное название; второе значение — число неоднозначных названий."""
    codes, first = collections.defaultdict(set), {}
    for r in ktru_rows:
        m = KTRU_RE.match(r["ktru_code"].strip())
        text = " ".join(r["text"].split())
        key = normalize(text)
        if not m or not key:
            continue
        codes[key].add(m.group(1))
        first.setdefault(key, text)
    out = [(next(iter(c)), first[k]) for k, c in codes.items() if len(c) == 1 and next(iter(c)) in leaf]
    return sorted(out), sum(len(c) > 1 for c in codes.values())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ktru", type=Path, required=True)
    p.add_argument("--okpd2", type=Path, default=Path("/data/okpd2.csv"))
    p.add_argument("--out", type=Path, default=Path("/data/ktru_names.csv"))
    a = p.parse_args()
    csv.field_size_limit(10 ** 9)  # характеристики позиций — длинный JSON в одной ячейке
    with a.okpd2.open(encoding="utf-8") as f:
        leaf = {r["code"] for r in csv.DictReader(f, delimiter=";") if r["is_leaf"] == "1"}
    with a.ktru.open(encoding="utf-8-sig") as f:
        rows, ambiguous = build(csv.DictReader(f), leaf)
    with a.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(["code", "text"])
        w.writerows(rows)
    print(f"{a.out}: {len(rows)} наименований, {len({c for c, _ in rows})} кодов; неоднозначных пропущено: {ambiguous}")


if __name__ == "__main__":
    main()
