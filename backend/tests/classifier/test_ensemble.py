import numpy as np
import pytest

from app.classifier.ensemble import EnsembleIndex


def unit(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def index(weight):
    # 11.11 и 22.22 делят синоним «папка» (одинаковые векторы); у 22.22 официальное наименование ближе к запросу
    codes = ["11.11", "11.11", "22.22", "22.22", "33.33"]
    texts = ["Скоросшиватели", "папка", "Папки картонные", "папка", "Бумага"]
    kinds = ["official", "synonym", "official", "synonym", "official"]
    main = np.stack([unit(1, 0, 0), unit(0, 1, 0), unit(0, 1, 1), unit(0, 1, 0), unit(0, 0, 1)])
    second = np.stack([unit(1, 0, 0), unit(1, 1, 0), unit(1, 1, 1), unit(1, 1, 0), unit(1, 0, 0)])
    titles = {"11.11": "Скоросшиватели", "22.22": "Папки", "33.33": "Бумага"}
    return EnsembleIndex(codes, texts, kinds, titles, main, second, weight)


def test_score_is_weighted_mean_and_best_text_per_code():
    idx = index(0.5)
    q = unit(0, 1, 0)
    sc = idx.scores(q, q)
    assert sc[1] == pytest.approx(0.5 * 1 + 0.5 * unit(1, 1, 0)[1], abs=2e-3)
    cands, _ = idx.search(q, q, 3)
    assert [c.code for c in cands][:2] == ["22.22", "11.11"]   # равенство по «папке» — решает официальное наименование
    assert cands[0].matched_text == "папка" and cands[0].title == "Папки"


def test_weight_zero_is_main_model_only():
    idx = index(0.0)
    cands, _ = idx.search(unit(0, 0, 1), unit(1, 0, 0), 1)
    assert cands[0].code == "33.33" and cands[0].score == pytest.approx(1.0, abs=2e-3)


def test_lookup_gives_score_for_codes_outside_top():
    idx = index(0.5)
    q = unit(0, 1, 0)
    cands, lookup = idx.search(q, q, 1)
    other = lookup("33.33")
    assert other.code == "33.33" and other.score < cands[0].score
    assert lookup("99.99") is None
