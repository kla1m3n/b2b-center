from app.classifier.matcher import code_covers, match, verdict
from app.npa.parser import NpaItemIn
from app.schemas import REGIME_BY_APPENDIX, Regime


def item(codes, appendix, item_no="1", exclusions=(), title="позиция", quota=None):
    return NpaItemIn(appendix=appendix, item_no=item_no, title=title, codes=list(codes),
                     regime=REGIME_BY_APPENDIX[appendix], quota=quota, exclusions=list(exclusions))


def test_covers_by_levels():
    assert code_covers("26.20", "26.20.11.110")
    assert code_covers("26.20.11.110", "26.20.11.110")
    assert code_covers("22", "22.29.29.190")
    assert not code_covers("26.2", "26.20.11")
    assert not code_covers("26.20.11", "26.20")
    assert not code_covers("26.20.1", "26.20.11.110")


def test_exclusion_overrides_parent():
    items = [item(["26.20"], 1, exclusions=["26.20.18"])]
    assert match("26.20.18.000", items) == []
    assert len(match("26.20.11.110", items)) == 1


def test_multiple_appendices_all_returned_strictest_first():
    items = [item(["17.12"], 3, quota=90), item(["17.12.14"], 2)]
    m = match("17.12.14.110", items)
    assert [x.regime for x in m] == [Regime.restriction, Regime.advantage]
    assert m[0].matched_code == "17.12.14" and m[1].quota == 90
    assert verdict(m) == Regime.restriction


def test_item_with_several_codes_matches_any():
    items = [item(["27.12.22", "27.12.31"], 1, item_no="30")]
    m = match("27.12.31.000", items)
    assert len(m) == 1 and m[0].matched_code == "27.12.31" and m[0].item_no == "30"


def test_not_covered_is_none():
    assert verdict(match("31.01.11.110", [item(["26.20"], 1)])) == Regime.none


def test_item_numbers_sorted_naturally():
    items = [item(["32.50"], 2, item_no="10"), item(["32.50"], 2, item_no="9"), item(["32.50"], 2, item_no="9_1")]
    assert [m.item_no for m in match("32.50.50.190", items)] == ["9", "9_1", "10"]
