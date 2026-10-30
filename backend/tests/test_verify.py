"""verify.py — 잔액 연쇄검증이 오독·오분류를 실제로 잡아내는지."""

import copy

import pytest

from data.sample_lines import SAMPLE_LINES
from passbook.lines import parse_lines
from passbook.verify import verify_balance_chain


@pytest.fixture
def rows():
    return parse_lines(SAMPLE_LINES)


def test_통장_전건_일치(rows):
    result = verify_balance_chain(rows, opening_balance=0)
    assert result["ok"]
    assert result["checked"] == len(rows)


def test_숫자_오독_검출(rows):
    # OCR이 64,000을 64,800으로 잘못 읽은 상황 (0 -> 8 오독)
    bad = copy.deepcopy(rows)
    bad[1]["찾으신금액"] = "₩64,800"
    result = verify_balance_chain(bad, opening_balance=0)
    assert not result["ok"]
    first = result["errors"][0]
    assert first["date"] == bad[1]["date"]
    assert first["차이"] == 800  # 실제잔액이 기대잔액보다 800 큼


def test_입출금_뒤집힘_검출(rows):
    # 지출을 입금으로 잘못 분류하면 부호가 뒤집혀 금액의 2배만큼 어긋난다
    bad = copy.deepcopy(rows)
    target = bad[1]
    amount = target["찾으신금액"]
    target["찾으신금액"], target["맡기신금액"] = None, amount
    result = verify_balance_chain(bad, opening_balance=0)
    assert not result["ok"]
    assert result["errors"][0]["차이"] == -2 * 64000


def test_빈_입력():
    result = verify_balance_chain([], opening_balance=0)
    assert result["ok"]
    assert result["checked"] == 0
