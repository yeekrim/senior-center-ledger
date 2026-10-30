"""OCR 한 줄(raw text) -> row dict 파싱.

지출/입금 판별은 bbox 좌표가 아니라 '토큰 순서'로 한다:
  지출: 날짜 적요 [₩금액 내역...] 잔액 거래점   <- 금액이 먼저
  입금: 날짜 적요 [내역... ₩금액] 잔액 거래점   <- 내역이 먼저

앞(날짜, 적요)과 뒤(잔액, 거래점)를 떼어낸 '가운데' 첫 토큰이
금액이면 지출, 글자면 입금이다. 판별이 틀리면 부호가 뒤집혀
잔액 연쇄검증(verify.py)에서 걸리므로 서로 교차검증이 된다.
"""

import re

# 금액 토큰: ₩736,000 / 736,000 / 736000 / 0  (₩·쉼표·온점·'원' 허용)
AMOUNT_RE = re.compile(r"^₩?\d{1,3}(?:[,.]\d{3})*원?$|^₩?\d+원?$")

# '₩4,000들녘직판장' 처럼 금액과 내역이 붙은 토큰을 분리.
# 붙는 쪽은 항상 한글 상호명이다. 알파벳까지 경계로 삼으면 '₩4S8,660'처럼
# 숫자를 알파벳으로 오독한 금액이 두 토큰으로 쪼개져 잘못 해석된다.
# ₩ 없이 찍는 통장도 있어 쉼표로 끊은 금액('11,000들녘')도 뗀다. '40정'처럼 쉼표 없는 숫자는 두지 않는다.
_GLUE_AFTER = re.compile(r"(₩[\d,.]+원?|(?<![\d,])\d{1,3}(?:,\d{3})+)(?=[가-힣])")   # 금액 뒤에 한글
_GLUE_BEFORE = re.compile(r"(?<=[가-힣])(?=₩\d)")             # 글자 뒤에 금액

DATE_RE = re.compile(r"^\d{8}$")


def is_amount(token: str) -> bool:
    return bool(AMOUNT_RE.match(token))


# 금액 끝에 붙은 칸막이선 · 괄호('₩6,000|', '₩8,500(주)'). 떼지 않으면 금액으로 보지 않아 줄을 버린다.
_STRAY_RULE = re.compile(r"(?<=\d)[|)\]](?=\s|$)")
_PUNCT_AFTER = re.compile(r"(₩[\d,.]+원?)(?=[(\[|)\]])")


def tokenize(line: str):
    line = _STRAY_RULE.sub("", line)
    line = _PUNCT_AFTER.sub(r"\1 ", line)
    line = _GLUE_AFTER.sub(r"\1 ", line)
    line = _GLUE_BEFORE.sub(" ", line)
    return line.split()


def parse_line(line: str):
    """거래 한 줄을 row dict로 변환. 거래 행이 아니면(안내문 등) None."""
    tokens = tokenize(line)
    if len(tokens) < 4 or not DATE_RE.match(tokens[0]):
        return None  # 날짜로 시작하지 않으면 거래 행이 아님 (통장 안내문 등)
    if is_amount(tokens[-1]) and ("₩" in tokens[-1] or "," in tokens[-1]):
        tokens.append("")                 # 끝이 잔액이면 거래점 칸이 비었다(거래점은 '48000'처럼 쉼표가 없다)

    date, 적요 = tokens[0], tokens[1]
    잔액, 거래점 = tokens[-2], tokens[-1]
    middle = tokens[2:-2]                 # 금액 + 사용내역 (순서가 판별 기준)
    if not middle:
        return None

    if is_amount(middle[0]):              # 금액이 먼저 -> 지출(찾으신금액)
        return {"date": date, "적요": 적요,
                "찾으신금액": middle[0], "맡기신금액": None,
                "사용내역": " ".join(middle[1:]), "잔액": 잔액, "거래점": 거래점}

    # 내역이 먼저 -> 입금(맡기신금액). 금액은 middle의 마지막 금액 토큰.
    if not is_amount(middle[-1]):
        return None                       # 가운데에 금액이 없으면 거래가 아님
    내역 = " ".join(middle[:-1])
    if not re.search(r"\d", middle[-1].replace("₩", "").replace("원", "")) \
            or middle[-1] in ("0", "₩0"):
        return None                       # '신규 0' 같은 개설 행은 거래가 아님
    return {"date": date, "적요": 적요,
            "찾으신금액": None, "맡기신금액": middle[-1],
            "사용내역": 내역, "잔액": 잔액, "거래점": 거래점}


def parse_lines(lines):
    """여러 줄을 파싱해 거래 row 리스트로. 비거래 행은 건너뛴다."""
    rows = []
    for line in lines:
        row = parse_line(line)
        if row is not None:
            rows.append(row)
    return rows
