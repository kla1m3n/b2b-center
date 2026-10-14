"""Конвертирует открытые выгрузки ОКПД2 и ПП 1875 в форматы проекта.

Источники (обновляются ежедневно из официальных публикаций):
  ОКПД2   — https://github.com/prog815/okpd2        (Росстат, ОК 034-2014)
  ПП 1875 — https://github.com/prog815/okpd2-pp1875 (Кодекс, актуальная редакция)

Использование:
  python scripts/import_open_data.py --okpd2 okpd2.json --okpd2-meta okpd2_meta.json \
      --pp pp1875_ref.json --pp-meta pp1875_meta.json --out ../data
"""
import argparse
import csv
import json
import re
from pathlib import Path

SUBITEM_RE = re.compile(r"(\d+_\d+)\.\s*(.+?)\s+(\d{2}(?:\.\d{1,3}){0,3})\s*(\(.*\))?\s*$", re.S)


def convert_okpd2(src: Path, meta: Path, out_dir: Path) -> int:
    rows = json.loads(src.read_text(encoding="utf-8"))
    out = out_dir / "okpd2.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["code", "title", "parent_code", "is_leaf"])
        for r in rows:
            parent = r["p"] if re.fullmatch(r"\d{2}(\.\d{1,3}){0,3}", r["p"] or "") else ""
            w.writerow([r["c"], r["n"].strip(), parent, int(r["l"])])
    m = json.loads(meta.read_text(encoding="utf-8"))
    (out_dir / "okpd2_meta.json").write_text(
        json.dumps({"version": m["version"], "source_url": m["source_page"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return len(rows)


def _items_from_ref(ref: list[dict]) -> list[dict]:
    items = []
    for r in ref:
        note = (r.get("x") or "").strip()
        sub = SUBITEM_RE.match(note) if note else None
        items.append({
            "appendix": r["a"], "item_no": str(r["p"]), "title": r["n"].strip(),
            "codes": r["c"], "quota": r["q"], "exclusions": [],
            "note": "" if sub else note,
        })
        if sub:  # подпозиция вида «31_1. …» склеена с примечанием в исходных данных
            items.append({
                "appendix": r["a"], "item_no": sub.group(1), "title": sub.group(2).strip(),
                "codes": [sub.group(3)], "quota": None, "exclusions": [],
                "note": (sub.group(4) or "").strip(),
            })
    return items


def convert_pp(src: Path, meta: Path, out_dir: Path) -> int:
    ref = json.loads(src.read_text(encoding="utf-8"))
    m = json.loads(meta.read_text(encoding="utf-8"))
    doc = {
        "title": f"ПП РФ № 1875 от 23.12.2024 (ред. на {m['source_date_display']})",
        "edition_date": m["source_date"],
        "source_url": m["source_url"],
        "items": _items_from_ref(ref),
    }
    npa_dir = out_dir / "npa"
    npa_dir.mkdir(parents=True, exist_ok=True)
    (npa_dir / "pp1875.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(doc["items"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--okpd2", type=Path, required=True)
    p.add_argument("--okpd2-meta", type=Path, required=True)
    p.add_argument("--pp", type=Path, required=True)
    p.add_argument("--pp-meta", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    print("ОКПД2:", convert_okpd2(a.okpd2, a.okpd2_meta, a.out))
    print("ПП 1875 позиций:", convert_pp(a.pp, a.pp_meta, a.out))


if __name__ == "__main__":
    main()
