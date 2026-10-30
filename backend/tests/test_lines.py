"""lines.py — 토큰 순서 기반 파싱의 edge 케이스."""

from passbook.lines import is_amount, parse_line, parse_lines, tokenize


def test_지출은_금액이_먼저():
    row = parse_line("20260521 40정 ₩64,000 새솔떡방 ₩672,000 36000")
    assert row["찾으신금액"] == "₩64,000"
    assert row["맡기신금액"] is None
    assert row["사용내역"] == "새솔떡방"


def test_입금은_내역이_먼저():
    row = parse_line("20260604 40정 승인취소-주식 ₩6,900 ₩438,660 36000")
    assert row["맡기신금액"] == "₩6,900"
    assert row["찾으신금액"] is None
    assert row["사용내역"] == "승인취소-주식"


def test_붙은_토큰_분리():
    # 실제 사진에 '₩4,000들녘직판장'처럼 금액과 상호가 한 덩어리인 줄이 있다
    assert tokenize("₩4,000들녘직판장")[:2] == ["₩4,000", "들녘직판장"]
    row = parse_line("20260521 40정 ₩4,000들녘직판장 ₩620,000 36000")
    assert row["찾으신금액"] == "₩4,000"
    assert row["사용내역"] == "들녘직판장"


def test_원화기호_없는_금액에_붙은_상호도_분리():
    # ₩ 없이 찍는 통장: '11,000들녘직판장'
    row = parse_line("20260711 40정 11,000들녘직판장 ₩3,132,470 본부")
    assert row["찾으신금액"] == "11,000"
    assert row["사용내역"] == "들녘직판장"


def test_금액_끝에_붙은_칸막이선과_괄호():
    row = parse_line("20260714 40정 ₩7,000| 가나상회 ₩682,350 27000")
    assert row["찾으신금액"] == "₩7,000"
    row = parse_line("20260714 40정 ₩5,500(주) 다라마트 ₩676,850 27000")
    assert row["찾으신금액"] == "₩5,500"
    assert row["잔액"] == "₩676,850"


def test_거래점_칸이_비면_끝이_잔액():
    row = parse_line("20260716 40정 3,000 마바상회 ₩673,850")
    assert row["찾으신금액"] == "3,000"
    assert row["잔액"] == "₩673,850"
    assert row["거래점"] == ""


def test_숫자로_시작하는_내역은_금액이_아님():
    # '2분기'가 금액으로 오인되면 입금이 지출로 뒤집힌다
    assert not is_amount("2분기")
    row = parse_line("20260312 40정 2분기 부식비 ₩736,000 ₩736,000 61834")
    assert row["맡기신금액"] == "₩736,000"
    assert row["사용내역"] == "2분기 부식비"


def test_신규_개설_행은_거래가_아님():
    assert parse_line("20260305 10유 신규 0 ₩0 본점") is None


def test_안내문과_헤더는_걸러짐():
    lines = [
        "보통예탁금",
        "년월일 적요 찾으신금액 맡기신금액 잔액 거래점",
        "우리 신협의 예탁금 및 적금은 법에 의거 원금과 소정의 이자를",
        "20260521 40정 ₩64,000 새솔떡방 ₩672,000 36000",
    ]
    rows = parse_lines(lines)
    assert len(rows) == 1
    assert rows[0]["date"] == "20260521"


def test_전체_fixture_거래_건수():
    from data.sample_lines import SAMPLE_LINES
    rows = parse_lines(SAMPLE_LINES)
    assert len(rows) == 19
