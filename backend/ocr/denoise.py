"""실사진 OCR 줄을 파싱 가능한 형태로 정규화.

fixture(이상적인 텍스트)와 달리 실제 엔진 출력에는 규칙적인 잡음이 있다.
실통장 사진에서 관찰한 종류들(아래 예시의 숫자는 지어낸 값):

  ₩ 오독      '₩64,000' -> '*64, 000' / '#3O, 00O' / 'w624,000' / '"13,0DO'
  숫자 속 공백 '₩104, 300', '₩4 , 000'
  0을 O/D로   '00O', '0DO', '47O,660'
  줄번호 붙음  통장 왼쪽 여백의 행번호가 날짜에 달라붙음: '120260521', '15 202606021'
  ₩가 8로     '₩672,000' -> '8672, 000' (첫 쉼표 앞이 4자리가 되어 식별 가능)
  적요 띄어짐  '40 정', '/ 40정' — 날짜와 적요 사이에 칸막이선 조각이 끼거나 띄어 읽힌다
  칸막이선     오른쪽 정렬된 잔액 끝에 세로선이 숫자로 붙는다: '₩2,418,6501'

여기서 고치는 것은 '기계적으로 확실한' 잡음뿐이다. 'S'를 6으로 읽는 식의
모호한 오독은 손대지 않고 남겨서, 잔액 연쇄검증이 사람에게 넘기도록 한다.
추측으로 숫자를 바꾸는 것보다 '모르겠다'고 표시하는 편이 회계에서는 안전하다.
"""

import re

_DATE = re.compile(r"20\d{6}")
_LEADING_DIGITS = re.compile(r"^\W*(\d{6,12})")

# ₩를 잘못 읽은 글자들. 숫자 바로 앞에 올 때만 통화기호로 본다.
_CURRENCY_CONFUSABLE = re.compile(r"""[#*wW"'`](?=\s*[\dOoDIl])""")

# 숫자 사이에 낀 공백: '109, 200' / '5 , 000' / '2O, 00O'
_NUMBER_SPACE = re.compile(r"(?<=[\dOoDIl])\s*,\s*(?=[\dOoDIl])")

# 금액 문맥에서만 글자를 숫자로 교정한다. ₩로 시작하거나, 쉼표로 자릿수를 끊은
# 숫자 덩어리. 상호명에는 '숫자,숫자' 형태가 없으므로 한글을 건드릴 위험이 없다.
_AMOUNT_RUN = re.compile(r"₩[\dOoDIl,]+|[\dOoDIl]+,[\dOoDIl,]+")
_CHAR_TO_DIGIT = str.maketrans({"O": "0", "o": "0", "D": "0", "I": "1", "l": "1"})

# 첫 쉼표 앞이 4자리인 수는 자릿수 규칙에 어긋난다 -> 맨 앞 글자는 ₩ 오독이다.
_FOUR_DIGIT_GROUP = re.compile(r"(?<![\d,₩])\d(\d{3},\d{3})")

# 마지막 쉼표 뒤가 4자리인 수도 자릿수 규칙에 어긋난다 -> 맨 끝 숫자는 오른쪽 칸막이선이다.
_RULE_AS_LAST_DIGIT = re.compile(r"(?<![\d,])(₩?\d{1,3}(?:,\d{3})+)\d(?![\d,])")

# 날짜 뒤 칸막이선 조각을 걷어내고, 띄어 읽힌 적요('40 정')를 붙인다. 안 그러면 칸이 한 칸씩 밀려 줄을 버린다.
_SPLIT_MEMO_CODE = re.compile(r"^(\d{8})\s*[|/)\]}(\[{!]*\s*(\d{2})\s*([가-힣])")

# 적요 자리('#0정')의 기호는 ₩가 아니다. ₩로 바꾸면 금액으로 떼어져 칸이 밀린다.
_MEMO_CODE_WON = re.compile(r"^(\d{8} )₩(?=\d[가-힣](\s|$))")


def _plausible_date(d: str) -> bool:
    return d.startswith("20") and "01" <= d[4:6] <= "12" and "01" <= d[6:8] <= "31"


def _repair_date(run: str):
    """행번호가 달라붙어 날짜 맨 앞 '2'가 묻힌 경우를 복구한다.

    관찰된 모양: 8행 '20260521' -> '80260521', 10행 -> '100260521'.
    둘 다 끝 7자리가 '0260521'이라 앞에 '2'를 되돌리면 유효한 날짜가 된다.
    """
    tail = run[-7:]
    if len(tail) == 7 and tail.startswith("0"):
        candidate = "2" + tail
        if _plausible_date(candidate):
            return candidate
    return None


def _cut_at(line: str, date: str, end: int) -> str:
    rest = line[end:].lstrip()
    rest = re.sub(r"^\d\s+", "", rest)   # 날짜 뒤에 떨어져 붙은 행번호 조각 ('202606081 40정')
    return f"{date} {rest}"


def _normalize_date_prefix(line: str) -> str:
    """줄 맨 앞의 행번호/따옴표 잡음을 걷어내고 날짜를 첫 토큰으로 만든다."""
    m = _DATE.search(line)
    if m and _plausible_date(m.group()):
        return _cut_at(line, m.group(), m.end())

    lead = _LEADING_DIGITS.match(line)
    if lead:
        repaired = _repair_date(lead.group(1))
        if repaired:
            return _cut_at(line, repaired, lead.end())
    return line


def _fix_amount_chars(line: str) -> str:
    return _AMOUNT_RUN.sub(lambda m: m.group().translate(_CHAR_TO_DIGIT), line)


def normalize_line(line: str) -> str:
    line = _normalize_date_prefix(line)
    line = _SPLIT_MEMO_CODE.sub(r"\1 \2\3", line)
    line = _CURRENCY_CONFUSABLE.sub("₩", line)
    line = _MEMO_CODE_WON.sub(r"\1#", line)
    line = _NUMBER_SPACE.sub(",", line)
    line = _fix_amount_chars(line)
    line = _FOUR_DIGIT_GROUP.sub(r"₩\1", line)
    line = _RULE_AS_LAST_DIGIT.sub(r"\1", line)   # ₩를 숫자로 읽은 앞자리를 먼저 고쳐야 쉼표 묶음이 보인다
    return line


def normalize_lines(lines):
    return [normalize_line(line) for line in lines]
