"""Сборка data/npa/pp1875.json (формат docs/npa-structure.md) из сверенной таблицы pp1875.csv.

pp1875.csv — 942 позиции всех трёх приложений, ред. 30.09.2026 (Контур.Норматив ред. 03.08.2026, сверка с
КонсультантПлюс + поправки ПП № 1201, 1236, 1264), с датами начала применения. Отличия от прежнего JSON:
  * исключённые позиции (прил. 2 поз. 109, 111, 112, 436–438) не попадают в базу. Раньше в их «коды» попадали
    числа из даты и номера постановления («исключена с 22 июля … от 13 июля» -> коды 22 и 13, «… от 18.12.2025» -> 18),
    и 280 кодов ОКПД2 (пряжа, изделия из пластмасс, полиграфия) получали ложное «ограничение»;
  * подпункты 82(1), 122(1)…122(6), 178(1)…178(11) и т.п. — отдельные позиции со своим номером
    (раньше их коды дописывались к основному пункту, и ссылка на пункт была неточной);
  * новые подпункты, которые ещё не действуют на дату --date, не включаются (82(1), 109(1), 109(2), 110(1)–(3),
    113(1)–(2) прил. 2 и 44(1) прил. 3 — с 01.01.2027); переформулированная поз. 113 прил. 2 остаётся с примечанием;
    доля прил. 3 поз. 43 с 01.01.2027 — 50%. На 01.01.2027 пересоберите файл с --date 2027-01-01 и загрузите как новую редакцию;
  * исключение кода 26.20.40.150 в прил. 2 поз. 205 (устройства ЧПУ — запрет по прил. 1 поз. 27).

    python scripts/build_npa_json.py --csv /data/npa/pp1875.csv --out /data/npa/pp1875.json [--date 2026-10-22]
"""
import argparse
import csv
import datetime as dt
import json
import re
from pathlib import Path

CODE_RE = re.compile(r"\d{2}(?:\.\d{1,3}){0,3}")


def ru_date(s: str) -> dt.date | None:
    return dt.datetime.strptime(s, "%d.%m.%Y").date() if s else None


def build(csv_path: Path, on: dt.date, title: str, source_url: str) -> dict:
    items, skipped = [], []
    with csv_path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            eff = ru_date(r.get("effective_from", ""))
            future = bool(eff and eff > on)
            if future and "(" in r["item"]:                         # новый подпункт, ещё не вступил в силу
                skipped.append(f"{r['appendix']}:{r['item']} (с {r['effective_from']})")
                continue
            quota = int(r["min_share"]) if r.get("min_share") else None
            note_parts = [p for p in (r.get("exceptions", ""), r.get("note", "")) if p]
            if r["appendix"] == "3" and r["item"] == "43" and on >= dt.date(2027, 1, 1):
                quota = 50                                              # ПП от 21.09.2026 № 1201
            if future:                                               # переформулированная позиция: до даты — прежняя редакция
                note_parts.append(f"Приведённая редакция применяется с {r['effective_from']}; до этой даты — прежняя редакция позиции")
            elif eff:
                note_parts.append(f"Применяется с {r['effective_from']}")
            items.append({
                "appendix": int(r["appendix"]), "item_no": r["item"], "title": r["name"],
                "codes": CODE_RE.findall(r["okpd2"]), "quota": quota,
                "exclusions": CODE_RE.findall(r.get("excl_okpd2", "")), "note": " ".join(note_parts),
            })
    return {"title": title, "edition_date": "2026-09-30", "source_url": source_url, "items": items}, skipped


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, default=Path("/data/npa/pp1875.csv"))
    p.add_argument("--out", type=Path, default=Path("/data/npa/pp1875.json"))
    p.add_argument("--date", default=dt.date.today().isoformat(), help="дата, на которую собирается действующая база")
    p.add_argument("--title", default="ПП РФ № 1875 от 23.12.2024 (ред. на 30 сентября 2026 года)")
    p.add_argument("--source-url", default="https://docs.cntd.ru/document/1310667825")
    a = p.parse_args()
    doc, skipped = build(a.csv, dt.date.fromisoformat(a.date), a.title, a.source_url)
    a.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    by_app = {n: sum(1 for i in doc["items"] if i["appendix"] == n) for n in (1, 2, 3)}
    print(f"{a.out}: {len(doc['items'])} позиций {by_app} на {a.date}; ещё не действуют: {', '.join(skipped) or '—'}")


if __name__ == "__main__":
    main()
