import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from build_npa_json import build  # noqa: E402

from app.config import get_settings  # noqa: E402

CSV = Path(get_settings().data_dir) / "npa" / "pp1875.csv"
MOVED = {"27.20.22", "31.01.1", "31.02.10", "31.09.12", "31.09.13"}  # ПП от 30.10.2026 № 1428: прил. 2 → прил. 1


def placed(on: dt.date) -> dict[str, tuple[int, str]]:
    """Код → (приложение, номер позиции) среди запретов и ограничений на дату."""
    doc, _ = build(CSV, on, "t", "u")
    return {i["codes"][0]: (i["appendix"], i["item_no"]) for i in doc["items"]
            if i["appendix"] < 3 and len(i["codes"]) == 1 and i["codes"][0] in MOVED}


def test_moved_items_stay_restriction_with_warning_until_effective_date():
    doc, skipped = build(CSV, dt.date(2026, 11, 11), "t", "u")
    assert {a for a, _ in placed(dt.date(2026, 11, 11)).values()} == {2}
    notes = [i["note"] for i in doc["items"] if i["appendix"] == 2 and i["item_no"] in ("139", "190")]
    assert len(notes) == 2 and all("запрет" in n and "1428" in n for n in notes)
    assert "1:31(1-1) (с 01.01.2027)" in skipped and "1:138(3) (с 01.07.2027)" in skipped


def test_batteries_move_to_ban_in_january_and_furniture_in_july_2027():
    jan, jul = placed(dt.date(2027, 1, 1)), placed(dt.date(2027, 7, 1))
    assert jan["27.20.22"] == (1, "31(1-1)") and jan["31.02.10"] == (2, "140")
    assert jul == {"27.20.22": (1, "31(1-1)"), "31.01.1": (1, "136(1)"), "31.02.10": (1, "136(2)"),
                   "31.09.12": (1, "138(2)"), "31.09.13": (1, "138(3)")}
