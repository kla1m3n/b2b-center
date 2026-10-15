from app.classifier.confidence import to_confidence


def test_confidence_sums_to_one_and_ranks():
    c = to_confidence([3.0, 1.0, 0.5], temperature=1.0)
    assert abs(sum(c) - 1) < 1e-6 and c[0] > c[1] > c[2]


def test_lower_temperature_sharpens():
    assert to_confidence([2.0, 1.0], temperature=0.5)[0] > to_confidence([2.0, 1.0], temperature=1.0)[0]


def test_empty_scores():
    assert to_confidence([], temperature=1.0) == []
