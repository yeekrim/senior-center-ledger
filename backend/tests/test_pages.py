"""pages.py — 여러 장의 통장 사진 이어붙이기.

약속: 페이지를 아무 순서로 줘도 잔액이 이어지는 순서로 합치고,
겹쳐 찍힌 구간은 잘라내되 정상적인 중복 거래는 보존한다.
"""

import pytest

from data.sample_lines import SAMPLE_LINES
from passbook.lines import parse_lines
from passbook.pages import infer_opening, merge_pages, page_closing, page_opening
from passbook.verify import verify_balance_chain


@pytest.fixture
def rows():
    return parse_lines(SAMPLE_LINES)


def test_시작잔액은_첫행_거래를_되돌려_구한다(rows):
    # 첫 거래는 입금 736,000 / 잔액 736,000 -> 그 전 잔액은 0
    assert page_opening(rows) == 0
    assert page_closing(rows) == 1145257


def test_순서대로_준_페이지(rows):
    merged, report = merge_pages([rows[:7], rows[7:13], rows[13:]])
    assert merged == rows
    assert report["order"] == [0, 1, 2]
    assert report["gaps"] == []


def test_순서를_섞어_줘도_잔액으로_복원(rows):
    pages = [rows[13:], rows[:7], rows[7:13]]      # 3, 1, 2번째 페이지 순으로 전달
    merged, report = merge_pages(pages)
    assert merged == rows
    assert report["order"] == [1, 2, 0]            # 원래 인덱스로 되짚어 정렬됨
    assert report["gaps"] == []


def test_합친_결과가_잔액_연쇄검증을_통과(rows):
    merged, _ = merge_pages([rows[13:], rows[:7], rows[7:13]])
    result = verify_balance_chain(merged, opening_balance=0)
    assert result["ok"]
    assert result["checked"] == len(rows)


def test_겹쳐_찍은_사진의_중복_구간_제거(rows):
    # 두 번째 사진이 첫 사진의 마지막 2행을 다시 찍은 경우
    merged, report = merge_pages([rows[:8], rows[6:13], rows[13:]])
    assert merged == rows
    assert report["dropped"] == 2
    assert report["gaps"] == []


def test_정상적인_중복_거래는_보존(rows):
    # 20260604 주식회사 해솔 ₩6,900 이 두 건 있다. 겹침 제거가 이걸 지우면 안 된다.
    merged, _ = merge_pages([rows[:7], rows[7:13], rows[13:]])
    해솔 = [r for r in merged
           if r["date"] == "20260604" and r.get("사용내역") == "주식회사 해솔"]
    assert len(해솔) == 2


def test_잔액이_끊기면_기록에_남는다(rows):
    # 가운데 페이지를 통째로 빠뜨린 채 올린 경우
    merged, report = merge_pages([rows[:7], rows[13:]])
    assert len(report["gaps"]) == 1
    gap = report["gaps"][0]
    assert gap["기대시작잔액"] == 513200      # 첫 페이지 끝 잔액
    assert gap["실제시작잔액"] == 431760      # 마지막 페이지 시작 잔액
    assert len(merged) == 7 + len(rows[13:])  # 있는 것은 버리지 않는다


def test_한_장만_줘도_동작(rows):
    merged, report = merge_pages([rows])
    assert merged == rows
    assert report["order"] == [0]


def test_빈_입력():
    merged, report = merge_pages([])
    assert merged == []
    assert report == {"order": [], "dropped": 0, "gaps": []}


def test_시작잔액_추정_신규부터_찍은_통장(rows):
    assert infer_opening([rows[13:], rows[:7], rows[7:13]]) == 0


def test_시작잔액_추정_중간부터_찍은_통장(rows):
    # 1페이지를 빼고 2, 3페이지만 찍었다 -> 2페이지 첫 거래 직전 잔액
    assert infer_opening([rows[13:], rows[7:13]]) == page_opening(rows[7:13])


def test_시작잔액_추정_겹쳐_찍은_통장(rows):
    assert infer_opening([rows[5:], rows[:8]]) == 0


def test_시작잔액_추정_빈_입력():
    assert infer_opening([]) == 0
