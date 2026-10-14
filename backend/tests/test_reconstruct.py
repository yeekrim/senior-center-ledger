"""reconstruct.py — 낱개 토큰을 원래 줄로 복원.

약속: y가 가까운 토큰끼리 같은 줄로 묶고, 줄 안에서는 x 순으로 정렬한다.
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


def test_빈_입력():
    assert lines_of([]) == []


def test_mock_응답_전체_복원():
    from ocr.mock_client import call_mock_ocr
    from data.sample_lines import SAMPLE_LINES

    assert fields_to_lines(call_mock_ocr(b"")) == SAMPLE_LINES
