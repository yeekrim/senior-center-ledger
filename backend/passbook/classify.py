"""입금을 보조금 / 이자 / 미정으로 나눈다.

경로당은 보조금 항목마다 통장을 따로 쓴다(운영비 · 부식비 · 냉난방비). 정산보고서의
'예산액(보조금)'과 '이자' 칸은 이 분류로 채운다.

  보조금  '2분기 부식비'처럼 '분기'가 붙고, 그 통장의 항목 이름이 들어간 입금
  이자    '결산이자'
  미정    그 밖의 모든 입금 — 캐쉬백, 승인취소, 개인 입금, 다른 항목 이름의 보조금 등

항목 이름까지 맞춰 보는 이유: 운영비 통장에 '2분기 냉난방비'가 들어온 적이 있다.
'분기'만 보고 보조금으로 넣으면 그 돈이 운영비 예산으로 잡힌다. 어느 칸에 넣을지는
통장만 보고 알 수 없으므로 사람에게 넘긴다.

미정을 억지로 분류하지 않는 것은 review.py와 같은 원칙이다. 회계에서는 틀린 답을
자신 있게 내놓는 것보다 모른다고 말하는 편이 안전하다.
"""

import re

from .parse import INTEREST_KEYWORD

SUBSIDY = "보조금"
INTEREST = "이자"
PENDING = "미정"

# 통장(보고서의 구분). 통장 종류는 여기서만 정한다 — 화면도 /api/accounts로 이 목록을 받는다.
#   이름: 정산보고서의 '구분' 칸에 적힌 이름
#   항목: 그 통장 보조금 입금의 사용내역에 들어가는 항목 이름
ACCOUNTS = {
    "운영비": {"이름": "운영비 (난방비 포함)", "항목": ("운영비",)},
    "부식비": {"이름": "부식비", "항목": ("부식비",)},
    "냉난방비": {"이름": "냉난방비 · 양곡비 (국비)", "항목": ("냉난방비", "양곡비")},
}

# 분기 숫자는 요구하지 않는다. 실사진 OCR에서 '3분기'가 '40정분기'처럼 숫자를 잃고
# 적요에 붙어 나온 적이 있다. 항목 이름까지 맞아야 하므로 이것만으로 오분류되지는 않는다.
QUARTER = "분기"


def _memo(row) -> str:
    # OCR에서 적요와 사용내역이 붙어 나오거나('40정2분기 부식비') 글자 사이에 공백이
    # 끼는 일('결산이 자')이 있어, 둘을 이어 붙이고 공백을 모두 지운 뒤 본다.
    return re.sub(r"\s", "", f"{row.get('적요', '')}{row.get('사용내역', '')}")


def classify_deposit(row, account: str) -> str:
    """입금 행 하나를 보조금 / 이자 / 미정으로 분류한다."""
    if account not in ACCOUNTS:
        raise ValueError(f"알 수 없는 통장: {account} (가능: {', '.join(ACCOUNTS)})")

    memo = _memo(row)
    if INTEREST_KEYWORD in memo:
        return INTEREST
    if QUARTER in memo and any(name in memo for name in ACCOUNTS[account]["항목"]):
        return SUBSIDY
    return PENDING
