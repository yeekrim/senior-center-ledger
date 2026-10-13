"""잔액 연쇄검증.

통장의 각 행은  이전잔액 + 입금 - 지출 = 현재잔액  이 성립해야 한다.
OCR 오독(숫자 잘못 읽음)이나 입금/지출 분류 오류(부호 뒤집힘)가 있으면
연쇄가 깨지므로, 어느 행부터 어긋나는지 짚어낼 수 있다.
"""

from .normalize import to_amount
from .parse import INTEREST_KEYWORD


def verify_balance_chain(rows, opening_balance=None):
    """row dict 리스트(문서 순서)를 검증한다.

    opening_balance: 첫 행 이전의 잔액. None이면 첫 행의 잔액을 기준점으로 삼는다.
    반환: {"ok": bool, "checked": n, "errors": [행별 오류 dict]}
    """
    errors = []
    prev = opening_balance
    checked = 0

    for i, r in enumerate(rows):
        입금액 = to_amount(r.get("맡기신금액"))
        지출액 = to_amount(r.get("찾으신금액"))
        잔액 = to_amount(r.get("잔액"))

        if prev is None:
            # 기준점: 첫 행은 검증할 이전잔액이 없으므로 잔액만 채택
            prev = 잔액
            continue

        expected = prev + 입금액 - 지출액
        checked += 1
        if expected != 잔액:
            errors.append({
                "index": i,
                "date": r["date"],
                "사용내역": r.get("사용내역", ""),
                "이전잔액": prev,
                "입금": 입금액,
                "지출": 지출액,
                "기대잔액": expected,
                "실제잔액": 잔액,
                "차이": 잔액 - expected,
            })
        prev = 잔액  # 다음 행은 통장에 찍힌 잔액 기준으로 이어서 검증

    return {"ok": not errors, "checked": checked, "errors": errors}
