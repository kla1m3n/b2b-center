"""Оценка точности на тестовом наборе → reports/eval.md.

Запуск: docker compose run --rm -v ./reports:/reports api python scripts/eval.py [--testset /data/eval/testset.csv]

Метрики:
  код top-1   — предсказанный код ОКПД2 совпадает с эталоном до уровня, указанного в эталоне;
  код top-3   — то же среди лучшего кода и двух альтернатив;
  вердикт     — режим ПП (запрет / ограничение / преимущество / не подпадает) совпал;
  пункты ПП   — множество «приложение:пункт» совпало полностью.
"""
import argparse
import csv
import time
from pathlib import Path

from app.classifier.pipeline import Pipeline
from app.config import get_settings
from app.db import SessionLocal
from app.models import ClassificationCache


def digits(code: str) -> str:
    return code.replace(".", "")


def code_ok(pred: str | None, expected: str) -> bool:
    return bool(pred) and digits(pred).startswith(digits(expected))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--testset", type=Path, default=Path(get_settings().data_dir) / "eval" / "testset.csv")
    p.add_argument("--out", type=Path, default=Path("/reports/eval.md"))
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()

    with a.testset.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    if a.limit:
        rows = rows[: a.limit]

    with SessionLocal() as s:  # без кэша, иначе меряем не модель
        s.query(ClassificationCache).delete()
        s.commit()
    pipe = Pipeline(get_settings(), SessionLocal)
    pipe.warmup()
    t0 = time.perf_counter()
    results = pipe.classify_many([r["name"] for r in rows])
    elapsed = time.perf_counter() - t0

    n = len(rows)
    top1 = top3 = verd = items = 0
    errors, bins = [], {}
    for r, res in zip(rows, results):
        pred = res.okpd2.code if res.okpd2 else None
        c1 = code_ok(pred, r["okpd2_expected"])
        c3 = c1 or any(code_ok(alt.code, r["okpd2_expected"]) for alt in res.alternatives[:2])
        v = res.verdict.value == r["regime_expected"]
        got_items = {f"{m.appendix}:{m.item_no}" for m in res.npa_matches}
        it = got_items == set(r["appendix_item_expected"].split())
        top1, top3, verd, items = top1 + c1, top3 + c3, verd + v, items + it
        b = min(int(res.confidence * 5), 4)
        bins.setdefault(b, []).append(c1)
        if not (c1 and v):
            errors.append((r["name"], r["okpd2_expected"], pred or "—", res.okpd2.title if res.okpd2 else "",
                           r["regime_expected"], res.verdict.value, res.confidence))

    s = get_settings()
    lines = [
        "# Оценка точности",
        "",
        f"Набор: `{a.testset.name}`, товаров: {n}. Модели: `{s.embed_model}` + `{s.rerank_model}`, "
        f"retrieve_k={s.retrieve_k}, rerank_k={s.rerank_k}, устройство: {s.device}.",
        "",
        "| Метрика | Значение |",
        "|---|---|",
        f"| Код ОКПД2, top-1 | **{top1 / n:.1%}** ({top1}/{n}) |",
        f"| Код ОКПД2, top-3 | {top3 / n:.1%} ({top3}/{n}) |",
        f"| Вердикт по ПП 1875 | **{verd / n:.1%}** ({verd}/{n}) |",
        f"| Пункты ПП совпали полностью | {items / n:.1%} ({items}/{n}) |",
        f"| Время на весь набор | {elapsed:.1f} с ({elapsed / n * 1000:.0f} мс/товар) |",
        "",
        "## Калибровка уверенности",
        "",
        "| Уверенность | Товаров | Точность кода |",
        "|---|---|---|",
    ]
    for b in sorted(bins):
        ok = bins[b]
        lines.append(f"| {b * 20}–{b * 20 + 20}% | {len(ok)} | {sum(ok) / len(ok):.0%} |")
    lines += ["", "## Ошибки", "", "| Товар | Эталон | Предсказано | Наименование | Вердикт эталон | Вердикт | Увер. |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {e[0]} | {e[1]} | {e[2]} | {e[3][:60]} | {e[4]} | {e[5]} | {e[6]:.0%} |" for e in errors]
    text = "\n".join(lines) + "\n"
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
