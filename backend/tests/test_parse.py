"""parse.py — 입금/지출/이자 3분류와 레코드 필드 순서."""

from data.sample_lines import SAMPLE_LINES
from passbook.lines import parse_lines
from passbook.parse import classify_rows


def _classified():
    return classify_rows(parse_lines(SAMPLE_LINES))


def test_분류_건수():
    입금, 지출, 이자 = _classified()
    assert len(입금) == 3   # 부식비 2회 + 승인취소 1회
    assert len(지출) == 15
    assert len(이자) == 1


def test_결산이자는_입금이_아니라_이자로():
    입금, _, 이자 = _classified()
    assert all("결산이자" not in rec[d][1] for rec in 입금 for d in rec)
    (rec,) = 이자
    assert rec["20260620"][2] == 21


def test_지출은_금액이_먼저():
    _, 지출, _ = _classified()
    first = 지출[0]["20260530"]
    assert first == ["40정", 71000, "행복방앗간", 778000, "45000"]


def test_입금은_내역이_먼저():
    입금, _, _ = _classified()
    first = 입금[0]["20260320"]
    assert first == ["40정", "2분기 부식비", 849000, 849000, "72519"]


def test_같은_날짜_중복_보존():
    # 5/30 하루에 지출 6건 — dict 키 충돌 없이 전부 보존되어야 한다
    _, 지출, _ = _classified()
    may30 = [rec for rec in 지출 if "20260530" in rec]
    assert len(may30) == 6
