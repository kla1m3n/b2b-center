"""Уверенность модели: калиброванная вероятность того, что выбранный код ОКПД2 верный.

P = sigmoid(w_score · s_top + w_margin · (s_top − s_second) + bias), где s — косинусная близость товара
к наименованию кода. Коэффициенты подбираются логистической регрессией на наборе для настройки
(scripts/eval.py --fit-confidence) и хранятся в настройках.
"""
import math
from collections.abc import Sequence

import numpy as np

Coef = tuple[float, float, float]


def calibrated(top: float, second: float, coef: Coef) -> float:
    w_score, w_margin, bias = coef
    z = w_score * top + w_margin * (top - second) + bias
    return 1 / (1 + math.exp(-max(min(z, 50.0), -50.0)))


def fit_calibration(features: Sequence[tuple[float, float]], labels: Sequence[int],
                    l2: float = 1e-3, steps: int = 20000, lr: float = 0.5) -> Coef:
    """features: (s_top, s_second). Логистическая регрессия градиентным спуском на стандартизованных признаках."""
    x = np.array([(t, t - s) for t, s in features], dtype=float)
    y = np.array(labels, dtype=float)
    mu, sd = x.mean(axis=0), x.std(axis=0) + 1e-9
    xs = (x - mu) / sd
    w, b = np.zeros(2), 0.0
    for _ in range(steps):
        p = 1 / (1 + np.exp(-(xs @ w + b)))
        w -= lr * (xs.T @ (p - y) / len(y) + l2 * w)
        b -= lr * float(np.mean(p - y))
    w_raw = w / sd
    return float(w_raw[0]), float(w_raw[1]), float(b - (w_raw * mu).sum())
