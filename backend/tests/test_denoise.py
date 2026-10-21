"""denoise.py — 실사진 OCR 잡음 정규화.

케이스는 전부 실통장 사진(IMG_4458.JPG)에서 실제로 관찰된 것이다.
"""

from data.real_ocr_lines import REAL_OCR_LINES
from ocr.denoise import normalize_line, normalize_lines
from passbook.lines import parse_lines
from passbook.verify import verify_balance_chain


def test_원화기호_오독_복원():
    # ₩를 # * w " 로 읽는다
    assert "₩71,000" in normalize_line("20260530 40정 *71, 000 행복방앗간 ₩778,000 45000")
    assert "₩746,000" in normalize_line("20260530 40정 ₩12,000 한창건어물 w746,000 45000")


def test_숫자_속_공백_제거():
    assert "₩109,200" in normalize_line("20260530 40정 #109, 200 다모아마트 ₩630,300 45000")
    assert "₩5,000" in normalize_line("20260530 40정 #5 , 000농산물직거래장 ₩741,000 45000")


def test_0을_O나_D로_읽은_것_교정():
    assert "₩590,940" in normalize_line("20260608 40정 ₩11,000농산물직거래장 #59O,940 45000")
    assert "₩11,000" in normalize_line("20260608 40정 \"11,0DO농산물직거래장 ₩590,940 45000")


def test_행번호가_날짜에_달라붙은_경우():
    # 통장 왼쪽 여백의 행번호가 날짜와 한 덩어리로 읽힌다
    assert normalize_line("120260530 40정 ₩1,500 푸른들청과 ₩739,500 45000").startswith("20260530 ")
    assert normalize_line("6 20260320 40정 부식비 ₩849,000 ₩849,000 72519").startswith("20260320 ")


def test_날짜_앞자리가_행번호에_묻힌_경우():
    # '20260530'이 '80260530'/'100260530'으로 읽혀 맨 앞 2가 사라진다
    assert normalize_line("80260530 40정 ₩20,000 한창건어물 ₩758,000 45000").startswith("20260530 ")
    assert normalize_line("100260530 40정 ₩5,000농산물직거래장 ₩741,000 45000").startswith("20260530 ")


def test_원화기호를_8로_읽은_경우():
    # 첫 쉼표 앞이 4자리인 수는 자릿수 규칙 위반 -> 맨 앞은 ₩ 오독이다
    assert "₩778,000" in normalize_line("20260530 40정 ₩71,000 행복방앗간 8778, 000 45000")


def test_띄어_읽힌_적요와_날짜_뒤_조각():
    # 적요가 '40 정'으로 갈리거나 칸막이선이 '/'로 끼면 칸이 밀려 줄을 통째로 버린다
    assert normalize_line("20260703 40 정 15,000 가나문구 ₩2,418,650 본부").startswith("20260703 40정 ")
    assert normalize_line("20260704 / 40정 8,000 다라상회 ₩2,410,650 본부").startswith("20260704 40정 ")


def test_잔액_끝에_붙은_칸막이선():
    # 마지막 쉼표 뒤가 4자리일 수는 없다. 오른쪽 세로선을 숫자로 읽은 것이다
    assert "₩2,418,650 " in normalize_line("20260703 40정 15,000 가나문구 ₩2,418,6501 본부")


def test_정상적인_금액은_건드리지_않는다():
    line = "20260610 40정 부식비 ₩849,000 ₩1,406,140 72519"
    assert normalize_line(line) == line


def test_거래_아닌_줄은_그대로():
    안내문 = "우리 신협의 예탁금 및 적금은 법에 의거 원금과 소정의 이자를"
    assert normalize_line(안내문) == 안내문


def test_실사진_전체_회귀():
    """실사진 26줄에서 거래 18건이 복원되고, 남은 오류는 3건이어야 한다.

    19건 중 1건(₩12,0D)l 한창건어물)은 금액이 복구 불가능하게 깨져서 버려지고,
    그 누락과 잔액 오독을 잔액 연쇄검증이 정확히 짚어낸다.
    """
    rows = parse_lines(normalize_lines(REAL_OCR_LINES))
    assert len(rows) == 18

    result = verify_balance_chain(rows, opening_balance=0)
    assert len(result["errors"]) == 3
    # 누락된 ₩12,000 거래를 검증이 금액까지 정확히 지목한다
    first = result["errors"][0]
    assert first["기대잔액"] - first["실제잔액"] == 12000
