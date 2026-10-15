import numpy as np

from app.classifier.confidence import calibrated, fit_calibration

COEF = (40.0, 60.0, -34.0)


def test_confidence_is_probability():
    for top, second in [(0.95, 0.80), (0.5, 0.5), (0.0, 0.0)]:
        assert 0.0 <= calibrated(top, second, COEF) <= 1.0


def test_higher_similarity_and_margin_mean_more_confidence():
    assert calibrated(0.90, 0.85, COEF) > calibrated(0.85, 0.80, COEF)
    assert calibrated(0.90, 0.80, COEF) > calibrated(0.90, 0.89, COEF)


def test_fit_separates_correct_from_wrong():
    rng = np.random.default_rng(0)
    good = np.column_stack([rng.normal(0.90, 0.01, 50), rng.normal(0.04, 0.01, 50)])
    bad = np.column_stack([rng.normal(0.82, 0.01, 50), rng.normal(0.005, 0.005, 50)])
    feats = [(t, t - m) for t, m in np.vstack([good, bad])]
    labels = [1] * 50 + [0] * 50
    coef = fit_calibration(feats, labels)
    assert calibrated(0.90, 0.86, coef) > 0.8
    assert calibrated(0.82, 0.815, coef) < 0.2
