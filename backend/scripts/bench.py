"""Замер скорости → reports/bench.md.

  * одиночный запрос: 20 уникальных товаров по одному, p50/p95 (критерий: < 5 с);
  * пакет: 100 уникальных товаров одним запросом (критерий: < 2 мин).

По умолчанию меряет через HTTP API (как пользователь), с --inprocess — напрямую конвейер.
Запуск: docker compose run --rm -v ./reports:/reports api python scripts/bench.py --url http://api:8000
"""
import argparse
import csv
import statistics
import time
from pathlib import Path

import httpx

from app.config import get_settings


def load_names(n: int) -> list[str]:
    ev = Path(get_settings().data_dir) / "eval"
    names = []
    for f in ("dev.csv", "holdout.csv", "testset.csv"):
        if (ev / f).exists():
            with (ev / f).open(encoding="utf-8") as fh:
                names += [r["name"] for r in csv.DictReader(fh, delimiter=";")]
    names = list(dict.fromkeys(names))
    run = str(time.time_ns())[-6:]  # уникальный суффикс → кэш не срабатывает
    return [f"{x} {run}{i}" for i, x in enumerate((names * (n // max(len(names), 1) + 1))[:n])]


def bench_http(url: str, singles: list[str], batch: list[str]) -> tuple[list[float], float]:
    with httpx.Client(base_url=url, timeout=300) as c:
        lat = []
        for name in singles:
            t = time.perf_counter()
            c.post("/api/classify", json={"name": name}).raise_for_status()
            lat.append(time.perf_counter() - t)
        t = time.perf_counter()
        job = c.post("/api/classify/batch", json={"names": batch}).raise_for_status().json()["job_id"]
        while c.get(f"/api/jobs/{job}").json()["status"] not in ("done", "failed"):
            time.sleep(0.5)
        return lat, time.perf_counter() - t


def bench_inprocess(singles: list[str], batch: list[str]) -> tuple[list[float], float]:
    from app.classifier.pipeline import Pipeline
    from app.db import SessionLocal

    pipe = Pipeline(get_settings(), SessionLocal)
    pipe.warmup()
    lat = []
    for name in singles:
        t = time.perf_counter()
        pipe.classify_many([name])
        lat.append(time.perf_counter() - t)
    t = time.perf_counter()
    pipe.classify_many(batch)
    return lat, time.perf_counter() - t


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://api:8000")
    p.add_argument("--inprocess", action="store_true")
    p.add_argument("--out", type=Path, default=Path("/reports/bench.md"))
    a = p.parse_args()
    names = load_names(120)
    singles, batch = names[:20], names[20:120]
    lat, batch_t = bench_inprocess(singles, batch) if a.inprocess else bench_http(a.url, singles, batch)
    lat.sort()
    p50, p95 = statistics.median(lat), lat[int(len(lat) * 0.95) - 1]
    s = get_settings()
    text = "\n".join([
        "# Замер скорости", "",
        f"Режим: {'конвейер напрямую' if a.inprocess else 'HTTP API'}, устройство: **{s.device}**, "
        f"модели: `{s.embed_model}` + `{s.rerank_model}`, rerank_k={s.rerank_k}.", "",
        "| Сценарий | Результат | Критерий | |", "|---|---|---|---|",
        f"| 1 товар, p50 | {p50:.2f} с | < 5 с | {'✅' if p50 < 5 else '❌'} |",
        f"| 1 товар, p95 | {p95:.2f} с | < 5 с | {'✅' if p95 < 5 else '❌'} |",
        f"| 100 товаров | {batch_t:.1f} с | < 120 с | {'✅' if batch_t < 120 else '❌'} |",
    ]) + "\n"
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
