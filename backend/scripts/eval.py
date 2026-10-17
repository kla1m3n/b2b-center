"""Оценка точности на тестовом наборе → reports/eval.md.

Запуск: docker compose run --rm -v ./reports:/reports api python scripts/eval.py [--testset /data/eval/testset.csv]

Метрики:
  код top-1   — предсказанный код ОКПД2 совпадает с эталоном до уровня, указанного в эталоне;
  код top-3   — то же среди лучшего кода и двух альтернатив;
  вердикт     — режим ПП (запрет / ограничение / преимущество / не подпадает) совпал;
  пункты ПП   — множество «приложение:пункт» совпало полностью.

Честность эталонов:
  - data/eval/label_fixes.csv — явные ошибки заказчиков в эталонных кодах (с причиной); в отчёте две строки:
    вердикт «как в наборе» и «с исправлениями»;
  - эталон — код группы (например, 31.02.1 «Мебель кухонная»): вердикт засчитывается, если он совпадает
    с вердиктом хотя бы одного конкретного кода этой группы (по одному групповому коду вердикт не определён).
"""
import argparse
import csv
import time
from pathlib import Path

from sqlalchemy import select

from app.classifier.matcher import match, verdict
from app.classifier.pipeline import Pipeline
from app.config import get_settings
from app.db import SessionLocal
from app.models import ClassificationCache, Okpd2Code
from app.npa.service import get_active_version, get_items


def digits(code: str) -> str:
    return code.replace(".", "")


def code_ok(pred: str | None, expected: str) -> bool:
    return bool(pred) and digits(pred).startswith(digits(expected))


def load_fixes(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {r["name"]: r["okpd2_fixed"].strip() for r in csv.DictReader(f, delimiter=";")}


class Expectations:
    """Эталонный вердикт и пункты ПП по коду — тем же matcher, что и в сервисе, по активной редакции."""

    def __init__(self) -> None:
        with SessionLocal() as s:
            v = get_active_version(s)
            self.items = get_items(s, v.id) if v else []
            self.leaves = [c for c in s.scalars(select(Okpd2Code.code).where(Okpd2Code.is_leaf.is_(True)))]
        self.leaf_set = set(self.leaves)

    def verdicts(self, code: str) -> set[str]:
        codes = [code] if code in self.leaf_set else [c for c in self.leaves if code_ok(c, code)] or [code]
        return {verdict(match(c, self.items)).value for c in codes}

    def items_of(self, code: str) -> set[str]:
        return {f"{m.appendix}:{m.item_no}" for m in match(code, self.items)}


def fit_confidence(pipe: Pipeline, rows: list[dict], results: list) -> None:
    """Уверенность калибруется на правильность ВЕРДИКТА по ПП (то, что важно тендерному специалисту),
    а не на точное совпадение кода до последней цифры: в реальных закупках заказчики часто ставят
    соседние коды, и калибровка по точному коду делала модель неоправданно неуверенной."""
    from app.classifier.confidence import fit_calibration
    from app.classifier.normalize import normalize
    from app.classifier.retriever import retrieve

    with SessionLocal() as s:
        cands = retrieve(s, pipe.embedder.encode_queries([normalize(r["name"]) for r in rows]), 2)
    feats = [(c[0].score, c[1].score) for c in cands]
    labels = [int(res.verdict.value == r["regime_expected"]) for res, r in zip(results, rows)]
    coef = fit_calibration(feats, labels)
    print(f"CONFIDENCE_COEF={list(round(x, 3) for x in coef)}  (вставить в app/config.py: confidence_coef)")
    pipe.s.confidence_coef = coef  # дальнейшие метрики этого прогона — с новой калибровкой


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--testset", type=Path, default=Path(get_settings().data_dir) / "eval" / "testset.csv")
    p.add_argument("--out", type=Path, default=Path("/reports/eval.md"))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--fixes", type=Path, default=Path(get_settings().data_dir) / "eval" / "label_fixes.csv")
    p.add_argument("--fit-confidence", action="store_true",
                   help="подобрать коэффициенты уверенности на этом наборе (только dev!)")
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

    if a.fit_confidence:
        fit_confidence(pipe, rows, results)

    fixes = load_fixes(a.fixes)
    exp = Expectations()
    n = len(rows)
    top1 = top3 = verd = items = verd_raw = fixed_n = 0
    errors, bins = [], {}
    for r, res in zip(rows, results):
        pred = res.okpd2.code if res.okpd2 else None
        verd_raw += res.verdict.value == r["regime_expected"]
        if r["name"] in fixes:
            fixed_n += 1
            r = {**r, "okpd2_expected": fixes[r["name"]]}
            r["regime_expected"] = "/".join(sorted(exp.verdicts(r["okpd2_expected"])))
            r["appendix_item_expected"] = " ".join(sorted(exp.items_of(r["okpd2_expected"])))
        c1 = code_ok(pred, r["okpd2_expected"])
        c3 = c1 or any(code_ok(alt.code, r["okpd2_expected"]) for alt in res.alternatives[:2])
        v = res.verdict.value in exp.verdicts(r["okpd2_expected"])
        got_items = {f"{m.appendix}:{m.item_no}" for m in res.npa_matches}
        it = got_items == set(r["appendix_item_expected"].split())
        top1, top3, verd, items = top1 + c1, top3 + c3, verd + v, items + it
        b = min(int(res.confidence * 5), 4)
        bins.setdefault(b, []).append((c1, v))
        if not (c1 and v):
            errors.append((r["name"], r["okpd2_expected"], pred or "—", res.okpd2.title if res.okpd2 else "",
                           r["regime_expected"], res.verdict.value, res.confidence))

    s = get_settings()
    lines = [
        "# Оценка точности",
        "",
        f"Набор: `{a.testset.name}`, товаров: {n}. Модель: `{s.embed_model}`, "
        f"retrieve_k={s.retrieve_k}, уверенность {tuple(round(x, 2) for x in s.confidence_coef)}, устройство: {s.device}.",
        "",
        "| Метрика | Значение |",
        "|---|---|",
        f"| Код ОКПД2, top-1 | **{top1 / n:.1%}** ({top1}/{n}) |",
        f"| Код ОКПД2, top-3 | {top3 / n:.1%} ({top3}/{n}) |",
        f"| Вердикт по ПП 1875 | **{verd / n:.1%}** ({verd}/{n}) |",
        f"| Вердикт как в наборе (без исправлений эталонов и учёта групп) | {verd_raw / n:.1%} ({verd_raw}/{n}) |",
        f"| Исправлено эталонов (`label_fixes.csv`) | {fixed_n} |",
        f"| Пункты ПП совпали полностью | {items / n:.1%} ({items}/{n}) |",
        f"| Время на весь набор | {elapsed:.1f} с ({elapsed / n * 1000:.0f} мс/товар) |",
        "",
        "## Калибровка уверенности",
        "",
        "| Уверенность | Товаров | Точность кода | Точность вердикта |",
        "|---|---|---|---|",
    ]
    for b in sorted(bins):
        ok = bins[b]
        lines.append(f"| {b * 20}–{b * 20 + 20}% | {len(ok)} | {sum(c for c, _ in ok) / len(ok):.0%} "
                     f"| {sum(v for _, v in ok) / len(ok):.0%} |")
    lines += ["", "## Ошибки", "", "| Товар | Эталон | Предсказано | Наименование | Вердикт эталон | Вердикт | Увер. |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {e[0]} | {e[1]} | {e[2]} | {e[3][:60]} | {e[4]} | {e[5]} | {e[6]:.0%} |" for e in errors]
    text = "\n".join(lines) + "\n"
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
