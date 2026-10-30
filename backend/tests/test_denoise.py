"""denoise.py — OCR 잡음 정규화.

잡음의 종류는 실통장 사진에서 관찰한 것이고, 줄에 든 날짜 · 금액 · 거래처는 모두 지어낸 값이다.
"""

from data.noisy_ocr_lines import NOISY_OCR_LINES
from ocr.denoise import normalize_line, normalize_lines
from passbook.lines import parse_lines
from passbook.verify import verify_balance_chain


def test_원화기호_오독_복원():
    # ₩를 # * w " 로 읽는다
    assert "₩64,000" in normalize_line("20260521 40정 *64, 000 새솔떡방 ₩672,000 36000")
    assert "₩624,000" in normalize_line("20260521 40정 ₩18,000 바다건어물 w624,000 36000")


def test_숫자_속_공백_제거():
    assert "₩104,300" in normalize_line("20260521 40정 #104, 300 모두마트 ₩513,200 36000")
    assert "₩4,000" in normalize_line("20260521 40정 #4 , 000들녘직판장 ₩620,000 36000")


def test_0을_O나_D로_읽은_것_교정():
    assert "₩470,660" in normalize_line("20260602 40정 ₩13,000들녘직판장 #47O,660 36000")
    assert "₩13,000" in normalize_line("20260602 40정 \"13,0DO들녘직판장 ₩470,660 36000")


def test_행번호가_날짜에_달라붙은_경우():
    # 통장 왼쪽 여백의 행번호가 날짜와 한 덩어리로 읽힌다
    assert normalize_line("120260521 40정 ₩2,500 초록청과 ₩617,500 36000").startswith("20260521 ")
    assert normalize_line("6 20260312 40정 부식비 ₩736,000 ₩736,000 61834").startswith("20260312 ")


def test_날짜_앞자리가_행번호에_묻힌_경우():
    # '20260521'이 '80260521'/'100260521'으로 읽혀 맨 앞 2가 사라진다
    assert normalize_line("80260521 40정 ₩30,000 바다건어물 ₩642,000 36000").startswith("20260521 ")
    assert normalize_line("100260521 40정 ₩4,000들녘직판장 ₩620,000 36000").startswith("20260521 ")


def test_원화기호를_8로_읽은_경우():
    # 첫 쉼표 앞이 4자리인 수는 자릿수 규칙 위반 -> 맨 앞은 ₩ 오독이다
    assert "₩672,000" in normalize_line("20260521 40정 ₩64,000 새솔떡방 8672, 000 36000")


def test_띄어_읽힌_적요와_날짜_뒤_조각():
    # 적요가 '40 정'으로 갈리거나 칸막이선이 '/'로 끼면 칸이 밀려 줄을 통째로 버린다
    assert normalize_line("20260708 40 정 23,000 가나문구 ₩3,152,470 본부").startswith("20260708 40정 ")
    assert normalize_line("20260709 / 40정 9,000 다라상회 ₩3,143,470 본부").startswith("20260709 40정 ")


def test_잔액_끝에_붙은_칸막이선():
    # 마지막 쉼표 뒤가 4자리일 수는 없다. 오른쪽 세로선을 숫자로 읽은 것이다
    assert "₩3,152,470 " in normalize_line("20260708 40정 23,000 가나문구 ₩3,152,4701 본부")


def test_원화기호를_숫자로_읽은_잔액의_칸막이선():
    # '4' + 잔액 + 칸막이선 '1': 앞자리를 ₩로 되돌린 뒤에야 마지막 묶음이 4자리로 보인다
    assert "₩682,350 " in normalize_line("20260714 40정 ₩7,000 가나상회 4682,3501 27000")


def test_적요_자리의_기호는_원화기호가_아니다():
    assert normalize_line("20260714 #0정 #7,000 가나상회 #682,350 27000").startswith("20260714 #0정 ₩7,000 ")


def test_정상적인_금액은_건드리지_않는다():
    line = "20260604 40정 부식비 ₩736,000 ₩1,167,760 61834"
    assert normalize_line(line) == line


def test_거래_아닌_줄은_그대로():
    안내문 = "우리 신협의 예탁금 및 적금은 법에 의거 원금과 소정의 이자를"
    assert normalize_line(안내문) == 안내문


def test_잡음_섞인_전체_회귀():
    """잡음 섞인 26줄에서 거래 18건이 복원되고, 남은 오류는 3건이어야 한다.

    19건 중 1건(₩15,0D)l 바다건어물)은 금액이 복구 불가능하게 깨져서 버려지고,
    그 누락과 잔액 오독을 잔액 연쇄검증이 정확히 짚어낸다.
    """
    rows = parse_lines(normalize_lines(NOISY_OCR_LINES))
    assert len(rows) == 18

    result = verify_balance_chain(rows, opening_balance=0)
    assert len(result["errors"]) == 3
    # 누락된 ₩15,000 거래를 검증이 금액까지 정확히 지목한다
    first = result["errors"][0]
    assert first["기대잔액"] - first["실제잔액"] == 15000
