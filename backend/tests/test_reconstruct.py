"""reconstruct.py — 낱개 토큰을 원래 줄로 복원.

약속: y가 가까운 토큰끼리 같은 줄로 묶고, 줄 안에서는 x 순으로 정렬한다.
날짜가 둘 이상 보이면 날짜마다 거래 한 줄이고, 줄 간격이 촘촘해도 거래끼리 합쳐지지 않는다.
"""

from ocr.reconstruct import fields_to_lines


def field(text, x, y, w=50, h=20):
    return {"inferText": text, "boundingPoly": {"vertices": [
        {"x": x, "y": y}, {"x": x + w, "y": y},
        {"x": x + w, "y": y + h}, {"x": x, "y": y + h},
    ]}}


def lines_of(fields):
    return fields_to_lines({"images": [{"fields": fields}]})


def test_토큰_순서가_섞여_와도_x순으로_복원():
    # 이 함수의 존재 이유. OCR은 읽은 순서대로 줄 뿐 좌우 순서를 보장하지 않는다.
    shuffled = [
        field("행복방앗간", 300, 100),
        field("20260530", 0, 100),
        field("₩71,000", 150, 100),
    ]
    assert lines_of(shuffled) == ["20260530 ₩71,000 행복방앗간"]


def test_기울어진_사진의_한_줄은_쪼개지지_않는다():
    # 비스듬히 찍으면 한 줄 안에서 y가 서서히 내려간다.
    # 기준을 줄의 첫 토큰에 고정하면 오차가 누적돼 중간에서 갈라진다.
    tilted = [
        field("20260530", 0, 100),
        field("40정", 100, 110),
        field("₩71,000", 200, 120),
        field("행복방앗간", 300, 130),
    ]
    assert lines_of(tilted) == ["20260530 40정 ₩71,000 행복방앗간"]


def test_줄_간격이_충분하면_다른_줄():
    two_rows = [
        field("20260530", 0, 100),
        field("행복방앗간", 100, 100),
        field("20260603", 0, 140),
        field("주식회사", 100, 140),
    ]
    assert lines_of(two_rows) == ["20260530 행복방앗간", "20260603 주식회사"]


def test_허용치는_글자_크기에_비례한다():
    # 같은 25px 낙차라도 글자가 작으면 다른 줄, 크면 같은 줄이어야 한다.
    # 허용치를 픽셀 절대값으로 박아두면 사진 해상도가 바뀔 때 무너진다.
    small = [field("가", 0, 100, h=20), field("나", 100, 125, h=20)]
    large = [field("가", 0, 100, h=60), field("나", 100, 125, h=60)]
    assert len(lines_of(small)) == 2
    assert len(lines_of(large)) == 1


def row(date, y, drop=0, x0=0, h=20):
    """통장 거래 한 줄: 날짜 · 적요 · 금액 · 내역 · 잔액 · 거래점. drop은 칸마다 내려가는 y(기울기)."""
    texts = [date, "40정", "₩12,000", "가나상회", "₩1,000,000", "45000"]
    return [field(t, x0 + i * 120, y + i * drop, w=100, h=h) for i, t in enumerate(texts)]


def test_기울어진_촘촘한_줄도_거래마다_나뉜다():
    # 이 방식의 존재 이유. 줄 간격이 촘촘한 통장이 조금만 기울어도, 한 줄의 오른쪽 끝 토큰과
    # 다음 줄의 왼쪽 토큰이 y로 가까워져 '직전 토큰과 가까우면 같은 줄'로는 거래가 합쳐진다.
    fields = row("20260511", 100, drop=3) + row("20260512", 124, drop=3) + row("20260513", 148, drop=3)
    lines = lines_of(fields)
    assert lines == [
        "20260511 40정 ₩12,000 가나상회 ₩1,000,000 45000",
        "20260512 40정 ₩12,000 가나상회 ₩1,000,000 45000",
        "20260513 40정 ₩12,000 가나상회 ₩1,000,000 45000",
    ]


def test_접힌_위아래_페이지가_서로_다르게_기울어도_나뉜다():
    top = [f for i, y in enumerate((100, 124, 148)) for f in row(f"2026050{i + 1}", y, drop=3)]
    bottom = [f for i, y in enumerate((300, 324, 348)) for f in row(f"2026060{i + 1}", y, drop=-3)]
    lines = lines_of(top + bottom)
    assert [l.split()[0] for l in lines] == [
        "20260501", "20260502", "20260503", "20260601", "20260602", "20260603"]
    assert all(len(l.split()) == 6 for l in lines)


def test_날짜_없는_머리글과_안내문은_제자리에_따로_남는다():
    fields = ([field("년월일", 0, 40), field("잔액", 480, 40)]
              + row("20260511", 100) + row("20260512", 124)
              + [field("사람이", 0, 200), field("신협", 120, 200)])
    assert lines_of(fields) == [
        "년월일 잔액",
        "20260511 40정 ₩12,000 가나상회 ₩1,000,000 45000",
        "20260512 40정 ₩12,000 가나상회 ₩1,000,000 45000",
        "사람이 신협",
    ]


def test_행번호가_붙거나_0을_O로_읽은_날짜도_기준점이_된다():
    fields = row("1220260511", 100) + row("2026O512", 124)
    assert [l.split()[0] for l in lines_of(fields)] == ["1220260511", "2026O512"]


def test_내역_칸의_날짜는_기준점으로_쓰지_않는다():
    # 내역에 날짜처럼 생긴 숫자가 있어도 그 자리에서 새 줄을 시작하지 않는다.
    fields = row("20260511", 100) + row("20260512", 124) + [field("20260101", 360, 112)]
    lines = lines_of(fields)
    assert len(lines) == 2


def test_빈_입력():
    assert lines_of([]) == []


def test_mock_응답_전체_복원():
    from ocr.mock_client import call_mock_ocr
    from data.sample_lines import SAMPLE_LINES

    assert fields_to_lines(call_mock_ocr(b"")) == SAMPLE_LINES
