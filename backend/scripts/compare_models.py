"""Сравнение моделей эмбеддингов (и реранкеров) на наборе для настройки → reports/models.md.

Индекс строится в памяти (numpy), поэтому БД не нужна. Лучше запускать на GPU:
  docker run --rm --gpus all -v hfcache:/hf -e HF_HOME=/hf ... b2b-center-api-gpu \
      python scripts/compare_models.py --embed intfloat/multilingual-e5-base deepvk/USER-bge-m3

Метрики: recall@k — эталонный код (до его уровня) среди k первых кандидатов (только коды нижнего уровня);
top-1 rerank — точность после переранжирования top-K кандидатов кросс-энкодером.
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
    p.add_argument("--rerank", nargs="*", default=[])
    p.add_argument("--rerank-k", type=int, default=10)
    p.add_argument("--data", type=Path, default=Path("/data"))
    p.add_argument("--testset", default="dev.csv")
    p.add_argument("--device", default="cuda")
    p.add_argument("--out", type=Path, default=Path("/reports/models.md"))
    a = p.parse_args()

    with (a.data / "okpd2.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    leaf = {r["code"] for r in rows if r["is_leaf"] == "1"}
    codes = [Okpd2Code(code=r["code"], title=r["title"], parent_code=r["parent_code"] or None) for r in rows]
    texts = [t for t in okpd2_texts(codes, read_synonyms(a.data / "okpd2_synonyms.csv")) if t[0] in leaf]
    titles = {r["code"]: r["title"] for r in rows}
    with (a.data / "eval" / a.testset).open(encoding="utf-8") as f:
        test = list(csv.DictReader(f, delimiter=";"))
    queries = [normalize(r["name"]) for r in test]
    expected = [r["okpd2_expected"] for r in test]

    lines = ["# Сравнение моделей", "", f"Набор: `{a.testset}` ({len(test)} товаров), индекс: {len(texts)} текстов "
             "кодов нижнего уровня.", "", "| Эмбеддинги | recall@1 | @5 | @10 | @20 | индекс, с | запрос, мс |",
             "|---|---|---|---|---|---|---|"]
    cands_by_model = {}
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
        cands_by_model[m] = cands
        rec = [np.mean([any(ok(c, e) for c in cs[:k]) for cs, e in zip(cands, expected)]) for k in (1, 5, 10, 20)]
        lines.append(f"| `{m}` | **{rec[0]:.1%}** | {rec[1]:.1%} | {rec[2]:.1%} | {rec[3]:.1%} | {t_index:.0f} | {t_query:.0f} |")
        print(lines[-1], flush=True)
        del emb

    if a.rerank:
        from app.classifier.reranker import Reranker

        lines += ["", f"| Эмбеддинги + реранкер (K={a.rerank_k}) | top-1 | с/пару |", "|---|---|---|"]
        for r_name in a.rerank:
            rr = Reranker(r_name, a.device)
            for m, cands in cands_by_model.items():
                pairs = [(q, titles[c]) for q, cs in zip(queries, cands) for c in cs[: a.rerank_k]]
                t = time.perf_counter()
                sc = rr.score(pairs)
                dt = (time.perf_counter() - t) / len(pairs)
                k = a.rerank_k
                top = [cs[max(range(k), key=lambda i: sc[j * k + i])] for j, cs in enumerate(cands)]
                acc = np.mean([ok(c, e) for c, e in zip(top, expected)])
                lines.append(f"| `{m}` + `{r_name}` | **{acc:.1%}** | {dt:.4f} |")
                print(lines[-1], flush=True)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
