"""reading.py — 작게 빨리 읽고, 잔액이 안 맞을 때만 크게 다시 읽는다.

약속: 첫 크기에서 이웃한 거래 사이의 잔액이 절반 이상 맞으면 다시 읽지 않는다. 그보다
적게 맞거나 거래를 못 읽었으면 다음 크기로 다시 읽고, 잔액이 맞아떨어진 이음매가 가장
많은 결과를 쓴다.
"""

import io

import pytest
from PIL import Image

import reading
from data.sample_lines import SAMPLE_LINES
from ocr.preprocess import shrink

BROKEN = SAMPLE_LINES[:12] + SAMPLE_LINES[13:]     # 거래 한 줄(12번)을 놓쳐 잔액 연쇄가 깨진다


def fake_ocr(by_size):
    """크기별로 정해 둔 줄을 돌려주는 가짜 OCR. 불린 크기를 기록한다."""
    calls = []

    def run(image_bytes, engine="easyocr", long_side=None, timings=None):
        calls.append(long_side)
        if timings is not None:
            timings.update({"OCR": 0.5, "줄복원": 0.01})
        return by_size[long_side]
    return run, calls


def test_첫_크기에서_잔액이_맞으면_다시_읽지_않는다(monkeypatch):
    run, calls = fake_ocr({1400: SAMPLE_LINES, None: BROKEN})
    monkeypatch.setattr(reading, "run_ocr_pipeline", run)
    page = reading.read_page(b"x")
    assert calls == [1400]
    assert page["크기"] == 1400
    assert [a["연쇄오류"] for a in page["시도"]] == [0]


def test_한두_군데만_어긋나면_다시_읽지_않는다(monkeypatch):
    run, calls = fake_ocr({1400: BROKEN, None: SAMPLE_LINES})
    monkeypatch.setattr(reading, "run_ocr_pipeline", run)
    page = reading.read_page(b"x")
    assert calls == [1400]                     # 원본으로 다시 읽으면 1분 안팎이 더 든다
    assert page["시도"][0]["연쇄오류"] == 1


def test_절반_넘게_어긋나면_원본으로_다시_읽는다(monkeypatch):
    # 거래 두 줄 중 하나를 놓쳐 하나뿐인 이음매가 어긋난 경우(실사진 냉난방비 통장)
    run, calls = fake_ocr({1400: SAMPLE_LINES[8:9] + SAMPLE_LINES[10:11], None: SAMPLE_LINES})
    monkeypatch.setattr(reading, "run_ocr_pipeline", run)
    page = reading.read_page(b"x")
    assert calls == [1400, None]
    assert page["크기"] == "원본"
    assert len(page["rows"]) == len(reading.parse_lines(SAMPLE_LINES))


def test_오류가_없어도_한_줄만_읽은_결과를_고르지_않는다(monkeypatch):
    # 실사진 운영비 통장: 작게 읽으면 6줄(오류 2), 원본은 1줄(오류 0). 오류 수로 고르면 1줄을 고른다.
    six_with_errors = SAMPLE_LINES[8:11] + SAMPLE_LINES[12:13] + SAMPLE_LINES[14:15] + SAMPLE_LINES[16:18]
    run, calls = fake_ocr({1400: six_with_errors, None: SAMPLE_LINES[8:9]})
    monkeypatch.setattr(reading, "run_ocr_pipeline", run)
    monkeypatch.setattr(reading, "RETRY_BELOW", 0.9)       # 다시 읽게 만들어 고르는 규칙을 본다
    page = reading.read_page(b"x")
    assert calls == [1400, None]
    assert page["크기"] == 1400


def test_거래를_하나도_못_읽으면_다시_읽는다(monkeypatch):
    run, calls = fake_ocr({1400: ["보통예탁금"], None: SAMPLE_LINES})
    monkeypatch.setattr(reading, "run_ocr_pipeline", run)
    assert reading.read_page(b"x")["크기"] == "원본"
    assert calls == [1400, None]


def test_단계별_시간을_돌려준다(monkeypatch):
    run, _ = fake_ocr({1400: SAMPLE_LINES, None: SAMPLE_LINES})
    monkeypatch.setattr(reading, "run_ocr_pipeline", run)
    시간 = reading.read_page(b"x")["시간"]
    assert {"OCR", "줄복원", "파싱", "합계"} <= set(시간)


@pytest.mark.parametrize("orientation, expected", [(1, (1400, 1050)), (6, (1050, 1400))])
def test_줄일_때_사진_회전을_먼저_적용한다(orientation, expected):
    # 휴대폰은 세로 사진을 가로로 저장하고 EXIF에 '90도 돌려서 보라'(6)고 적는다
    exif = Image.Exif()
    exif[0x0112] = orientation
    buf = io.BytesIO()
    Image.new("RGB", (4000, 3000), "white").save(buf, format="JPEG", exif=exif)
    assert Image.open(io.BytesIO(shrink(buf.getvalue(), 1400))).size == expected


@pytest.mark.parametrize("raw, expected", [("1400,원본", (1400, None)), ("1800", (1800,)), (" 1200 , 원본 ", (1200, None))])
def test_읽기_크기_설정을_읽는다(raw, expected):
    from settings import parse_sizes
    assert parse_sizes(raw) == expected


@pytest.mark.parametrize("raw", ["", "1400,abc", "0", "-5"])
def test_잘못된_읽기_크기_설정은_거부(raw):
    from settings import parse_sizes
    with pytest.raises(ValueError):
        parse_sizes(raw)
