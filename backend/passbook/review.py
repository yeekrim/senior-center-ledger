"""잔액이 안 맞는 행의 원인을 가려내고, 사람이 고칠 거리를 만들어 준다.

verify.py는 '이 행에서 잔액이 안 맞는다'까지만 말한다. 하지만 안 맞는 이유는
크게 두 가지이고, 사람이 해야 할 일이 서로 다르다:

  잔액오독   통장에 찍힌 잔액을 OCR이 잘못 읽었다. 거래 자체는 맞다.
             -> 잔액 숫자만 고치면 된다. 올바른 값도 계산해서 알려줄 수 있다.
  거래누락   거래 한 줄을 통째로 놓쳤다. 찍힌 잔액은 맞다.
             -> 빠진 거래를 사람이 채워 넣어야 한다. 금액은 계산으로 알 수 있다.

구분하는 근거는 '다음 행'이다. 잔액을 기대값으로 바꿨을 때 다음 행이 맞아떨어지면
잔액을 잘못 읽은 것이고, 통장에 찍힌 값 그대로일 때 다음 행이 맞아떨어지면
그 값은 옳고 앞에서 거래를 빠뜨린 것이다.

둘 다 아니면 억지로 단정하지 않고 '확인필요'로 넘긴다. 회계에서는 틀린 답을
자신 있게 내놓는 것보다 모른다고 말하는 편이 안전하다. 제안은 어디까지나
제안이며, 값을 자동으로 반영하지 않는다 — 최종 판단은 사람이 한다.
"""

from .normalize import to_amount

OK = "정상"
BALANCE_MISREAD = "잔액오독"
MISSING_ROW = "거래누락"
UNKNOWN = "확인필요"


def _amounts(row):
    return to_amount(row["맡기신금액"]), to_amount(row["찾으신금액"]), to_amount(row["잔액"])


def _chains(prev_balance: int, row) -> bool:
    입금, 지출, 잔액 = _amounts(row)
    return prev_balance + 입금 - 지출 == 잔액


def _classify(rows, index: int, expected: int, actual: int) -> str:
    nxt = rows[index + 1] if index + 1 < len(rows) else None
    if nxt is None:
        return UNKNOWN
    if _chains(expected, nxt):
        return BALANCE_MISREAD      # 잔액을 기대값으로 고치면 뒤가 맞는다
    if _chains(actual, nxt):
        return MISSING_ROW          # 찍힌 잔액이 옳다 -> 앞에서 거래를 빠뜨렸다
    return UNKNOWN


def _suggestion(status: str, expected: int, actual: int):
    if status == BALANCE_MISREAD:
        return {"필드": "잔액", "제안값": expected,
                "설명": f"잔액을 {actual:,}이 아니라 {expected:,}으로 읽어야 앞뒤가 맞습니다."}
    if status == MISSING_ROW:
        차이 = expected - actual
        종류 = "지출" if 차이 > 0 else "입금"
        return {"필드": "앞에 거래 추가", "제안값": abs(차이),
                "설명": f"이 행 앞에 {종류} {abs(차이):,}원짜리 거래가 빠진 것 같습니다."}
    return {"필드": None, "제안값": None,
            "설명": "앞뒤 잔액이 모두 맞지 않습니다. 통장 사진을 직접 확인해 주세요."}


def review_transactions(rows, opening_balance: int = 0):
    """행마다 상태와 수정 제안을 붙인 검토 목록을 만든다.

    반환: {"items": [...], "summary": {상태별 건수}}
    """
    items = []
    prev = opening_balance

    for index, row in enumerate(rows):
        입금, 지출, 잔액 = _amounts(row)
        expected = prev + 입금 - 지출
        status = OK if expected == 잔액 else _classify(rows, index, expected, 잔액)

        item = {
            "index": index,
            "date": row["date"],
            "적요": row.get("적요", ""),
            "사용내역": row.get("사용내역", ""),
            "입금": 입금,
            "지출": 지출,
            "잔액": 잔액,
            "거래점": row.get("거래점", ""),
            "상태": status,
            "이전잔액": prev,
            "기대잔액": expected,
        }
        if status != OK:
            item["제안"] = _suggestion(status, expected, 잔액)
        items.append(item)

        # 잔액을 잘못 읽은 것으로 판정했으면, 잘못된 값이 아니라 바로잡은 값을
        # 다음 행에 물려준다. 그러지 않으면 뒤따르는 멀쩡한 행들이 줄줄이
        # 오류로 표시되고, 사람은 진짜 고칠 곳이 어디인지 알 수 없게 된다.
        prev = expected if status == BALANCE_MISREAD else 잔액

    summary = {"전체": len(items)}
    for status in (OK, BALANCE_MISREAD, MISSING_ROW, UNKNOWN):
        summary[status] = sum(1 for item in items if item["상태"] == status)
    return {"items": items, "summary": summary}
