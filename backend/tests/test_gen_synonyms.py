import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from gen_synonyms import resolve  # noqa: E402

ROWS = [
    {"code": "16.21.13", "title": "Плиты древесно-стружечные", "is_leaf": "0"},
    {"code": "16.21.13.000", "title": "Плиты древесно-стружечные и аналогичные", "is_leaf": "1"},
    {"code": "20.30.11", "title": "Материалы лакокрасочные", "is_leaf": "0"},
    {"code": "20.30.11.110", "title": "Лаки на основе акриловых полимеров", "is_leaf": "1"},
    {"code": "20.30.11.120", "title": "Краски на основе акриловых полимеров", "is_leaf": "1"},
]


def test_group_synonym_goes_to_leaf_code():
    # раньше синоним записывался на код группы и терялся: поиск строится только по кодам нижнего уровня
    assert resolve(ROWS, "16.21.13", "") == ["16.21.13.000"]


def test_pattern_selects_matching_leaf():
    assert resolve(ROWS, "20.30.11", r"^Краски") == ["20.30.11.120"]


def test_unknown_prefix_is_unresolved():
    assert resolve(ROWS, "99.99.99", "") == []
