"""통장 하나의 반기 거래 -> 보조금 정산보고서에 옮겨 적을 값.

정산보고서(구청 제출)는 통장(운영비 · 부식비 · 냉난방비)마다 두 표를 쓴다:

  월별 집행내역  1~6월(또는 7~12월) 각각  수입액(보조금·이자 등) / 집행액 / 잔액
  총괄          예산액(보조금) / 집행액 / 집행잔액 = 예산액 - 집행액 / 이자

보고서는 어르신이 직접 쓰고, 이 모듈은 칸에 들어갈 숫자만 돌려준다.

미정 입금(classify.PENDING)은 사람이 둘 중 하나로 정한다:

  수입  월별 수입액에 더한다. 총괄표에는 칸이 없으므로 '기타수입'으로 따로 알려준다.
  차감  집행액에서 뺀다(승인취소 · 반환처럼 나간 돈이 되돌아온 경우).

어느 쪽이든 '시작잔액 + 수입액 - 집행액 = 기말 통장잔액'이 성립한다. 아직 정하지
않은 입금이 남아 있으면 그 금액만큼 검산이 어긋나므로 '완료'가 되지 않는다.
"""

from .classify import ACCOUNTS, INTEREST, PENDING, SUBSIDY, classify_deposit
from .normalize import to_amount
from .pages import page_opening
from .verify import verify_balance_chain

TO_INCOME = "수입"
TO_DEDUCT = "차감"
DECISIONS = (TO_INCOME, TO_DEDUCT)

HALVES = {"상반기": range(1, 7), "하반기": range(7, 13)}


def _period(year: int, half: str):
    if half not in HALVES:
        raise ValueError(f"알 수 없는 반기: {half} (가능: {', '.join(HALVES)})")
    months = HALVES[half]
    return months, f"{year}{months[0]:02d}01", f"{year}{months[-1]:02d}31"


def _opening(before, inside) -> int:
    """기간 시작 잔액. 기간 앞 거래가 있으면 그 마지막 잔액, 없으면 첫 거래를 되돌린 값."""
    if before:
        return to_amount(before[-1]["잔액"])
    if inside:
        return page_opening(inside)
    return 0


def settle(rows, account: str, year: int, half: str,
           opening_balance=None, decisions=None):
    """rows(문서 순서, 검토를 마친 거래)에서 반기 정산값을 계산한다.

    opening_balance: None이면 통장에서 계산한다(_opening 참조).
    decisions: {rows의 인덱스: "수입" | "차감"} — 미정 입금에 대한 사람의 결정.
    """
    if account not in ACCOUNTS:
        raise ValueError(f"알 수 없는 통장: {account} (가능: {', '.join(ACCOUNTS)})")
    months, start, end = _period(year, half)
    decisions ={int(k): v for k, v in (decisions or {}).items()}
    for index, choice in decisions.items():
        if choice not in DECISIONS:
            raise ValueError(f"{index}번 행: 알 수 없는 결정 {choice} (가능: {', '.join(DECISIONS)})")

    indexed = list(enumerate(rows))
    before = [r for _, r in indexed if r["date"] < start]
    inside = [(i, r) for i, r in indexed if start <= r["date"] <= end]
    opening = _opening(before, [r for _, r in inside]) if opening_balance is None else opening_balance

    monthly = {m: {"수입액": 0, "집행액": 0, "잔액": None} for m in months}
    totals = {SUBSIDY: 0, INTEREST: 0, "기타수입": 0, "집행액": 0}
    pending = []

    for index, row in inside:
        month = monthly[int(row["date"][4:6])]
        입금 = to_amount(row.get("맡기신금액"))
        출금 = to_amount(row.get("찾으신금액"))

        month["집행액"] += 출금
        totals["집행액"] += 출금

        if 입금:
            kind = classify_deposit(row, account)
            if kind == PENDING:
                choice = decisions.get(index)
                pending.append({"index": index, "date": row["date"],
                                 "사용내역": row.get("사용내역", ""), "금액": 입금, "결정": choice})
                if choice == TO_INCOME:
                    month["수입액"] += 입금
                    totals["기타수입"] += 입금
                elif choice == TO_DEDUCT:
                    month["집행액"] -= 입금
                    totals["집행액"] -= 입금
            else:
                month["수입액"] += 입금
                totals[kind] += 입금

        month["잔액"] = to_amount(row["잔액"])

    # 미정 입금이 아닌 행에 대한 결정은 화면과 서버가 서로 다른 행을 가리킨다는 뜻이다.
    # 조용히 무시하면 사람이 정한 결정이 엉뚱하게 빠지므로 거절한다.
    stray = sorted(set(decisions) - {p["index"] for p in pending})
    if stray:
        raise ValueError(f"미정 입금이 아닌 행에 대한 결정: {stray}")

    # 거래가 없는 달의 잔액은 직전 달 잔액을 그대로 이어받는다.
    carried = opening
    for m in months:
        if monthly[m]["잔액"] is None:
            monthly[m]["잔액"] = carried
        carried = monthly[m]["잔액"]

    total_income = sum(v["수입액"] for v in monthly.values())
    closing = carried
    computed = opening + total_income - totals["집행액"]
    chain = verify_balance_chain([r for _, r in inside], opening_balance=opening)
    undecided = [p for p in pending if p["결정"] is None]

    return {
        "통장": account,
        "기간": {"연도": year, "반기": half, "시작월": months[0], "끝월": months[-1]},
        "월별": [{"월": m, **monthly[m]} for m in months],
        "합계": {"수입액": total_income, "집행액": totals["집행액"]},
        "총괄": {
            "예산액": totals[SUBSIDY],
            "집행액": totals["집행액"],
            "집행잔액": totals[SUBSIDY] - totals["집행액"],
            "이자": totals[INTEREST],
            "기타수입": totals["기타수입"],
        },
        "미정": pending,
        "검산": {
            "시작잔액": opening,
            "계산잔액": computed,
            "통장잔액": closing,
            "일치": computed == closing,
            "잔액연쇄": chain["ok"],
        },
        "완료": not undecided and computed == closing and chain["ok"],
    }
