"""classify.py · settlement.py — 정산보고서에 옮겨 적을 값.

약속:
  - 보조금은 'N분기' + 그 통장의 항목 이름일 때만, 이자는 '결산이자'일 때만 인정한다.
  - 그 밖의 입금은 미정으로 남기고, 사람이 '수입' 또는 '차감'을 정해야 완료된다.
  - 어떤 결정을 내려도 시작잔액 + 수입액 - 집행액 = 기말 통장잔액 이 성립한다.
"""

import pytest

from passbook.classify import INTEREST, PENDING, SUBSIDY, classify_deposit
from passbook.settlement import TO_DEDUCT, TO_INCOME, settle


def row(date, 내역, 출금=None, 입금=None, 잔액=None):
    return {"date": date, "적요": "40정", "찾으신금액": 출금, "맡기신금액": 입금,
            "사용내역": 내역, "잔액": 잔액, "거래점": "48000"}


# 가상의 운영비 통장: 다른 항목 보조금, 캐쉬백, 승인취소, 7월 거래가 섞여 있다.
운영비 = [
    row("20260320", "2분기 운영비", 입금="₩1,000,000", 잔액="₩1,000,000"),    # 0 보조금
    row("20260320", "2분기 냉난방비", 입금="₩200,000", 잔액="₩1,200,000"),    # 1 미정
    row("20260405", "생활용품점", 출금="₩100,000", 잔액="₩1,100,000"),        # 2
    row("20260506", "캐쉬백지급-매", 입금="₩500", 잔액="₩1,100,500"),         # 3 미정
    row("20260610", "동네마트", 출금="₩8,000", 잔액="₩1,092,500"),            # 4
    row("20260610", "승인취소-동네", 입금="₩8,000", 잔액="₩1,100,500"),       # 5 미정
    row("20260610", "동네마트", 출금="₩8,000", 잔액="₩1,092,500"),            # 6
    row("20260620", "결산이자", 입금="₩30", 잔액="₩1,092,530"),               # 7 이자
    row("20260702", "대형마트", 출금="₩50,000", 잔액="₩1,042,530"),           # 8 하반기
]

ALL_DECIDED = {1: TO_INCOME, 3: TO_INCOME, 5: TO_DEDUCT}


# ---- classify ----

@pytest.mark.parametrize("account, 내역, expected", [
    ("부식비", "2분기 부식비", SUBSIDY),
    ("운영비", "3분기 운영비추", SUBSIDY),
    ("냉난방비", "3분기 양곡비", SUBSIDY),
    ("운영비", "2분기 냉난방비", PENDING),   # 다른 항목 이름 -> 사람이 정한다
    ("부식비", "결산이자", INTEREST),
    ("부식비", "승인취소-주식", PENDING),
    ("운영비", "캐쉬백지급-매", PENDING),
    ("운영비", "홍길동", PENDING),
])
def test_입금_분류(account, 내역, expected):
    assert classify_deposit(row("20260101", 내역, 입금="₩1"), account) == expected


def test_적요에_붙은_보조금도_인식():
    r = {"date": "20260320", "적요": "40정2분기", "사용내역": "부식비", "맡기신금액": "₩1"}
    assert classify_deposit(r, "부식비") == SUBSIDY


@pytest.mark.parametrize("적요, 내역, expected", [
    ("40정분기", "부식비", SUBSIDY),     # 실사진 OCR: '3분기'의 숫자를 잃고 적요에 붙었다
    ("40증분기", "부식비", SUBSIDY),
    ("40정", "결산이 자", INTEREST),     # 실사진 OCR: 글자 사이에 공백
    ("40정승인", "취소-주식", PENDING),
])
def test_실사진_OCR_잡음에도_분류(적요, 내역, expected):
    r = {"date": "20260610", "적요": 적요, "사용내역": 내역, "맡기신금액": "₩1"}
    assert classify_deposit(r, "부식비") == expected


def test_모르는_통장은_거부():
    with pytest.raises(ValueError):
        classify_deposit(row("20260101", "2분기 부식비", 입금="₩1"), "간식비")


# ---- settle ----

def test_미정이_남으면_완료되지_않는다():
    result = settle(운영비, "운영비", 2026, "상반기")
    assert [p["index"] for p in result["미정"]] == [1, 3, 5]
    assert all(p["결정"] is None for p in result["미정"])
    assert result["완료"] is False
    assert result["검산"]["통장잔액"] - result["검산"]["계산잔액"] == 200_000 + 500 + 8_000


def test_결정을_마치면_검산이_맞는다():
    result = settle(운영비, "운영비", 2026, "상반기", decisions=ALL_DECIDED)
    assert result["완료"] is True
    assert result["검산"] == {"시작잔액": 0, "계산잔액": 1_092_530, "통장잔액": 1_092_530,
                            "일치": True, "잔액연쇄": True}


def test_월별표():
    result = settle(운영비, "운영비", 2026, "상반기", decisions=ALL_DECIDED)
    monthly = {m["월"]: m for m in result["월별"]}
    assert [m["월"] for m in result["월별"]] == [1, 2, 3, 4, 5, 6]
    assert monthly[1] == {"월": 1, "수입액": 0, "집행액": 0, "잔액": 0}
    assert monthly[3] == {"월": 3, "수입액": 1_200_000, "집행액": 0, "잔액": 1_200_000}
    assert monthly[4] == {"월": 4, "수입액": 0, "집행액": 100_000, "잔액": 1_100_000}
    assert monthly[5] == {"월": 5, "수입액": 500, "집행액": 0, "잔액": 1_100_500}
    # 출금 8,000 두 건은 집행액, 취소 8,000은 '차감'으로 정했다 -> 집행액 8,000
    assert monthly[6] == {"월": 6, "수입액": 30, "집행액": 8_000, "잔액": 1_092_530}
    assert result["합계"] == {"수입액": 1_200_530, "집행액": 108_000}


def test_총괄표():
    result = settle(운영비, "운영비", 2026, "상반기", decisions=ALL_DECIDED)
    assert result["총괄"] == {"예산액": 1_000_000, "이월금": 0, "보조금": 1_000_000,
                            "집행액": 108_000, "집행잔액": 892_000,
                            "이자": 30, "기타수입": 200_500}


def test_취소를_수입으로_정해도_검산은_맞는다():
    decisions = {**ALL_DECIDED, 5: TO_INCOME}
    result = settle(운영비, "운영비", 2026, "상반기", decisions=decisions)
    assert result["완료"] is True
    assert result["합계"] == {"수입액": 1_208_530, "집행액": 116_000}


def test_하반기는_앞_거래의_잔액에서_시작한다():
    result = settle(운영비, "운영비", 2026, "하반기")
    assert result["검산"]["시작잔액"] == 1_092_530
    assert result["월별"][0] == {"월": 7, "수입액": 0, "집행액": 50_000, "잔액": 1_042_530}
    assert result["월별"][-1]["잔액"] == 1_042_530
    assert result["미정"] == []
    assert result["완료"] is True


def test_중간부터_찍은_통장은_첫_거래를_되돌려_시작잔액을_구한다():
    rows = 운영비[2:8]       # 4월부터 찍은 사진
    result = settle(rows, "운영비", 2026, "상반기", decisions={1: TO_INCOME, 3: TO_DEDUCT})
    assert result["검산"]["시작잔액"] == 1_200_000
    assert result["월별"][0]["잔액"] == 1_200_000     # 1월은 시작잔액을 이어받는다
    assert result["완료"] is True


def test_잔액이_끊기면_완료되지_않는다():
    rows = [dict(r) for r in 운영비]
    rows[2]["잔액"] = "₩1,000,000"   # 잘못 읽은 잔액
    result = settle(rows, "운영비", 2026, "상반기", decisions=ALL_DECIDED)
    assert result["검산"]["잔액연쇄"] is False
    assert result["완료"] is False


def test_잘못된_결정과_반기는_거부():
    with pytest.raises(ValueError):
        settle(운영비, "운영비", 2026, "상반기", decisions={1: "보류"})
    with pytest.raises(ValueError):
        settle(운영비, "운영비", 2026, "1분기")


def test_미정이_아닌_행에_대한_결정은_거부():
    with pytest.raises(ValueError, match=r"\[0\]"):
        settle(운영비, "운영비", 2026, "상반기", decisions={**ALL_DECIDED, 0: TO_INCOME})


def test_하반기_예산액에는_상반기_이월금을_더한다():
    rows = 운영비[:8] + [
        row("20260710", "3분기 운영비", 입금="₩500,000", 잔액="₩1,592,530"),
        row("20260720", "대형마트", 출금="₩92,530", 잔액="₩1,500,000"),
    ]
    총괄 = settle(rows, "운영비", 2026, "하반기")["총괄"]
    assert 총괄["이월금"] == 1_092_530
    assert 총괄["보조금"] == 500_000
    assert 총괄["예산액"] == 1_592_530
    assert 총괄["집행잔액"] == 1_500_000      # 통장 잔액과 같다(이자·기타수입이 없을 때)
