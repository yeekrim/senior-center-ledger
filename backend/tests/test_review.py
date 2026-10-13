"""review.py — 잔액 불일치의 원인 분류와 수정 제안.

약속: 안 맞는 행마다 '잔액을 잘못 읽었는지' vs '거래를 빠뜨렸는지'를 가려내고,
사람이 고칠 수 있는 구체적인 값을 제시한다. 모르면 모른다고 한다.
"""

from data.real_ocr_lines import REAL_OCR_LINES
from ocr.denoise import normalize_lines
from passbook.lines import parse_lines
from passbook.review import (BALANCE_MISREAD, MISSING_ROW, OK, UNKNOWN,
                             review_transactions)


def row(date, 입금=None, 지출=None, 잔액=None, 내역=""):
    return {"date": date, "적요": "40정", "맡기신금액": 입금, "찾으신금액": 지출,
            "사용내역": 내역, "잔액": 잔액, "거래점": "45000"}


def test_전부_맞으면_정상():
    rows = [row("20260101", 입금="1,000", 잔액="1,000"),
            row("20260102", 지출="300", 잔액="700")]
    result = review_transactions(rows, opening_balance=0)
    assert result["summary"][OK] == 2
    assert all("제안" not in item for item in result["items"])


def test_잔액오독_감지와_제안값():
    # 두 번째 행의 잔액이 700인데 70으로 읽혔다. 세 번째 행은 700 기준으로 맞다.
    rows = [row("20260101", 입금="1,000", 잔액="1,000"),
            row("20260102", 지출="300", 잔액="70"),
            row("20260103", 지출="200", 잔액="500")]
    items = review_transactions(rows, opening_balance=0)["items"]
    assert items[1]["상태"] == BALANCE_MISREAD
    assert items[1]["제안"]["필드"] == "잔액"
    assert items[1]["제안"]["제안값"] == 700


def test_잔액오독_다음_행은_정상으로_유지():
    """바로잡은 값을 다음 행에 물려줘야 멀쩡한 행이 줄줄이 오류로 표시되지 않는다."""
    rows = [row("20260101", 입금="1,000", 잔액="1,000"),
            row("20260102", 지출="300", 잔액="70"),
            row("20260103", 지출="200", 잔액="500")]
    items = review_transactions(rows, opening_balance=0)["items"]
    assert items[2]["상태"] == OK


def test_거래누락_감지와_금액():
    # 두 행 사이에 지출 250짜리 거래가 빠졌다. 찍힌 잔액들은 모두 옳다.
    rows = [row("20260101", 입금="1,000", 잔액="1,000"),
            row("20260102", 지출="300", 잔액="450"),   # 1000-250-300 = 450
            row("20260103", 지출="50", 잔액="400")]
    items = review_transactions(rows, opening_balance=0)["items"]
    assert items[1]["상태"] == MISSING_ROW
    assert items[1]["제안"]["제안값"] == 250
    assert "지출" in items[1]["제안"]["설명"]


def test_누락된_입금도_구분():
    rows = [row("20260101", 입금="1,000", 잔액="1,000"),
            row("20260102", 지출="300", 잔액="1,200"),  # 500 입금이 빠짐
            row("20260103", 지출="200", 잔액="1,000")]
    items = review_transactions(rows, opening_balance=0)["items"]
    assert items[1]["상태"] == MISSING_ROW
    assert items[1]["제안"]["제안값"] == 500
    assert "입금" in items[1]["제안"]["설명"]


def test_마지막_행_오류는_단정하지_않는다():
    # 뒤에 비교할 행이 없으면 원인을 가릴 수 없다
    rows = [row("20260101", 입금="1,000", 잔액="1,000"),
            row("20260102", 지출="300", 잔액="999")]
    items = review_transactions(rows, opening_balance=0)["items"]
    assert items[1]["상태"] == UNKNOWN
    assert items[1]["제안"]["제안값"] is None


def test_실사진_회귀():
    """실통장 18건 중 사람이 볼 곳은 2건, 나머지는 정상이어야 한다."""
    rows = parse_lines(normalize_lines(REAL_OCR_LINES))
    result = review_transactions(rows, opening_balance=0)

    assert result["summary"] == {"전체": 18, OK: 16, BALANCE_MISREAD: 1,
                                 MISSING_ROW: 1, UNKNOWN: 0}

    누락 = next(i for i in result["items"] if i["상태"] == MISSING_ROW)
    assert 누락["제안"]["제안값"] == 12000      # 인식 실패한 ₩12,000 한창건어물

    오독 = next(i for i in result["items"] if i["상태"] == BALANCE_MISREAD)
    assert 오독["제안"]["제안값"] == 564940     # 통장에 실제로 찍힌 잔액
