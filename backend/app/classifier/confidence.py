"""Перевод оценок реранкера в вероятности (уверенность модели)."""
import math


def to_confidence(scores: list[float], temperature: float) -> list[float]:
    """Softmax с температурой по кандидатам. Температура подбирается на тестовом наборе (scripts/eval.py)."""
    if not scores:
        return []
    m = max(scores)
    exps = [math.exp((s - m) / temperature) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]
