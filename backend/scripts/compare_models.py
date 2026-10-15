"""Сравнение моделей эмбеддингов (и реранкеров) на наборе для настройки → reports/models.md.

Индекс строится в памяти (numpy), поэтому БД не нужна. Лучше запускать на GPU:
  docker run --rm --gpus all -v hfcache:/hf -e HF_HOME=/hf ... b2b-center-api-gpu \
      python scripts/compare_models.py --embed intfloat/multilingual-e5-base deepvk/USER-bge-m3

Метрики: recall@k — эталонный код (до его уровня) среди k первых кандидатов (только коды нижнего уровня);
(реранкер bge-reranker-v2-m3 проверен и убран: ухудшал top-1 — reports/rerank10.md, rerank20.md).
"""
import argparse
import csv
import time
from pathlib import Path

import numpy as np

from app.classifier.embedder import Embedder
from app.classifier.normalize import normalize
from app.models import Okpd2Code
from app.seed import okpd2_texts, read_synonyms


def ok(code: str, expected: str) -> bool:
    return code.replace(".", "").startswith(expected.replace(".", ""))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--embed", nargs="+", required=True)
    p.add_argument("--data", type=Path, default=Path("/data"))
    p.add_argument("--testset", default="dev.csv")
    p.add_argument("--device", default="cuda")
    p.add_argument("--out", type=Path, default=Path("/reports/models.md"))
    a = p.parse_args()

    with (a.data / "okpd2.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    leaf = {r["code"] for r in rows if r["is_leaf"] == "1"}
    codes = [Okpd2Code(code=r["code"], title=r["title"], parent_code=r["parent_code"] or None, is_leaf=r["is_leaf"] == "1")
             for r in rows]
    texts = [t for t in okpd2_texts(codes, read_synonyms(a.data / "okpd2_synonyms.csv")) if t[0] in leaf]
    with (a.data / "eval" / a.testset).open(encoding="utf-8") as f:
        test = list(csv.DictReader(f, delimiter=";"))
    queries = [normalize(r["name"]) for r in test]
    expected = [r["okpd2_expected"] for r in test]

    lines = ["# Сравнение моделей", "", f"Набор: `{a.testset}` ({len(test)} товаров), индекс: {len(texts)} текстов "
             "кодов нижнего уровня.", "", "| Эмбеддинги | recall@1 | @5 | @10 | @20 | индекс, с | запрос, мс |",
             "|---|---|---|---|---|---|---|"]
    for m in a.embed:
        emb = Embedder(m, a.device)
        t = time.perf_counter()
        P = emb.encode_passages([x[1] for x in texts])
        t_index = time.perf_counter() - t
        t = time.perf_counter()
        Q = emb.encode_queries(queries)
        t_query = (time.perf_counter() - t) / len(queries) * 1000
        sims = Q @ P.T
        cands = []
        for row in sims:
            seen, out = set(), []
            for i in np.argsort(-row):
                c = texts[i][0]
                if c not in seen:
                    seen.add(c)
                    out.append(c)
                if len(out) == 20:
                    break
            cands.append(out)
        rec = [np.mean([any(ok(c, e) for c in cs[:k]) for cs, e in zip(cands, expected)]) for k in (1, 5, 10, 20)]
        lines.append(f"| `{m}` | **{rec[0]:.1%}** | {rec[1]:.1%} | {rec[2]:.1%} | {rec[3]:.1%} | {t_index:.0f} | {t_query:.0f} |")
        print(lines[-1], flush=True)
        del emb

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
