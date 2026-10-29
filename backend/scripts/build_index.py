"""Предрассчитывает эмбеддинги ОКПД2 (+ синонимы) в data/index/<model>.npz, чтобы первый запуск был быстрым.

Запуск в контейнере: python scripts/build_index.py [--model intfloat/multilingual-e5-base]

--reuse — векторы текстов, которые уже есть в файле индекса, берутся из него, считаются только новые тексты.
Вектор зависит только от текста, поэтому после правки кодов в okpd2_synonyms.csv индекс переразмечается
за секунды, без пересчёта всех 16 тыс. текстов.
"""
import argparse
import csv
from pathlib import Path

import numpy as np

from app.classifier.embedder import Embedder
from app.config import get_settings
from app.models import Okpd2Code
from app.seed import index_name, okpd2_texts, read_synonyms


def main() -> None:
    s = get_settings()
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=s.embed_model)
    p.add_argument("--data", type=Path, default=Path(s.data_dir))
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--reuse", action="store_true", help="взять готовые векторы из --out, посчитать только новые тексты")
    a = p.parse_args()
    with (a.data / "okpd2.csv").open(encoding="utf-8") as f:
        codes = [Okpd2Code(code=r["code"], title=r["title"], parent_code=r["parent_code"] or None, is_leaf=r["is_leaf"] == "1")
                 for r in csv.DictReader(f, delimiter=";")]
    texts = okpd2_texts(codes, read_synonyms(a.data / "okpd2_synonyms.csv"))
    backend = s.embed_backend if a.model == s.embed_model else "torch"  # как в Embedder
    out = a.out or a.data / "index" / index_name(a.model, backend)
    known: dict[str, np.ndarray] = {}
    if a.reuse and out.exists():
        z = np.load(out)
        known = dict(zip(z["texts"].tolist(), z["vectors"]))
    new = sorted({t[1] for t in texts} - known.keys())
    if new:
        known.update(zip(new, Embedder(a.model, s.device).encode_passages(new).astype(np.float16)))
    vecs = np.stack([known[t[1]] for t in texts])
    print(f"посчитано заново: {len(new)} текстов")
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out,
        codes=np.array([t[0] for t in texts]), texts=np.array([t[1] for t in texts]),
        kinds=np.array([t[2] for t in texts]), vectors=vecs.astype(np.float16),
    )
    print(f"{out}: {len(texts)} текстов, размерность {vecs.shape[1]}")


if __name__ == "__main__":
    main()
