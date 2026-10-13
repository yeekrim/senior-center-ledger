"""aggregate.py — 월별 합계."""

from data.sample_lines import SAMPLE_LINES
from passbook.aggregate import monthly_totals
from passbook.lines import parse_lines
from passbook.parse import classify_rows


def test_실통장_월별_합계():
    입금, 지출, 이자 = classify_rows(parse_lines(SAMPLE_LINES))
    monthly = monthly_totals(입금, 지출, 이자)
    assert monthly == {
        "03": [849000, 0, 0],
        "05": [0, 218700, 0],
        "06": [856800, 105800, 21],
    }


def test_빈_입력():
    assert monthly_totals([], [], []) == {}
