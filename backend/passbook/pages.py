"""여러 장의 통장 사진을 하나의 연속된 거래 목록으로 잇는다.

페이지 순서를 사용자가 알려주지 않아도 된다 — 잔액이 근거가 된다.
각 페이지의 '시작 잔액'은 첫 행의 거래를 되돌려 계산할 수 있고
(첫행잔액 - 입금 + 지출), 이전 페이지의 '끝 잔액'과 맞물리는 페이지가
다음 페이지다. 잔액 항등식이 페이지 순서까지 정해주는 셈이라 사진을
아무 순서로 올려도 된다.

이음새는 두 종류다:
  맞물림  앞 페이지의 끝 잔액 == 뒤 페이지의 시작 잔액. 그대로 이어 붙인다.
  겹침    사진을 겹쳐 찍어 같은 거래가 두 장에 모두 나온다. 이때는 뒤 페이지의
          시작 잔액이 앞 페이지 '중간' 값이라 맞물림으로는 찾을 수 없다.
          앞 페이지의 꼬리와 뒤 페이지의 머리가 연속으로 같은 구간을 찾아 잘라낸다.

겹침을 처리할 때 전체를 훑어 중복을 지우면 안 된다 — 같은 날 같은 가게에서 같은
금액을 두 번 쓴 거래(예: 같은 날 같은 가게에서 ₩6,900씩 두 번)가 정상인데,
구별할 방법이 없어 하나를 잃는다. 그래서 이음새에서 연속으로 겹치는 구간만 잘라낸다.

어느 쪽으로도 이을 수 없으면 날짜순으로 붙이고 끊긴 지점을 report에 남긴다.
사람이 확인해야 할 곳을 감추지 않는 것이 이 프로젝트의 원칙이다.
"""

from .normalize import to_amount

MAX_SEAM_OVERLAP = 12   # 이음새에서 겹침을 찾아볼 최대 행 수


def page_opening(rows) -> int:
    """페이지의 시작 잔액. 첫 행의 거래를 되돌려 계산한다."""
    first = rows[0]
    return (to_amount(first["잔액"])
            - to_amount(first["맡기신금액"])
            + to_amount(first["찾으신금액"]))


def page_closing(rows) -> int:
    return to_amount(rows[-1]["잔액"])


def infer_opening(pages) -> int:
    """사진 묶음 전체의 시작 잔액을 통장에서 구한다.

    첫 페이지는 '다른 어떤 페이지의 끝 잔액과도 이어지지 않는' 페이지다. 그런 페이지가
    여럿이면(겹쳐 찍었거나 중간이 빠졌을 때) 첫 거래 날짜가 가장 이른 것을 고른다.
    통장을 '신규'부터 찍었다면 0이 나오고, 하반기처럼 중간부터 찍었다면 그 직전 잔액이 나온다.
    첫 행 잔액을 잘못 읽으면 이 값도 틀리지만, 그때는 둘째 행에서 잔액 연쇄가 깨져 드러난다.
    """
    pages = [p for p in pages if p]
    if not pages:
        return 0
    closings = {page_closing(p) for p in pages}
    starts = [p for p in pages if page_opening(p) not in closings] or pages
    return page_opening(min(starts, key=lambda p: p[0]["date"]))


def _row_key(row):
    return (row["date"], row.get("사용내역", ""),
            to_amount(row["찾으신금액"]), to_amount(row["맡기신금액"]),
            to_amount(row["잔액"]))


def _seam_overlap(merged, page) -> int:
    """merged의 꼬리와 page의 머리가 연속으로 겹치는 행 수. 긴 겹침을 우선한다."""
    limit = min(len(merged), len(page), MAX_SEAM_OVERLAP)
    for k in range(limit, 0, -1):
        if [_row_key(r) for r in merged[-k:]] == [_row_key(r) for r in page[:k]]:
            return k
    return 0


def _pick_next(remaining, merged, balance):
    """다음 페이지와 겹침 행 수를 고른다. 반환: (항목, 겹침수, 끊김여부)"""
    match = next((item for item in remaining
                  if page_opening(item[1]) == balance), None)
    if match is not None:
        return match, 0, False

    if merged:
        for item in remaining:
            overlap = _seam_overlap(merged, item[1])
            if overlap:
                return item, overlap, False

    return min(remaining, key=lambda item: item[1][0]["date"]), 0, True


def merge_pages(pages, opening_balance: int = 0):
    """여러 페이지를 잔액 순서대로 이어 하나의 거래 목록으로 만든다.

    반환: (합쳐진 rows, report)
    report: {"order": 원래 인덱스 순서, "dropped": 이음새에서 제거한 중복 행 수,
             "gaps": 잔액이 이어지지 않은 이음새}
    """
    remaining = [(i, p) for i, p in enumerate(pages) if p]
    merged, order, gaps, dropped = [], [], [], 0
    balance = opening_balance

    while remaining:
        item, overlap, broken = _pick_next(remaining, merged, balance)
        if broken:
            gaps.append({
                "앞페이지": order[-1] if order else None,
                "뒤페이지": item[0],
                "기대시작잔액": balance,
                "실제시작잔액": page_opening(item[1]),
            })

        remaining.remove(item)
        order.append(item[0])
        page = item[1]

        if not merged:
            merged = list(page)
        else:
            dropped += overlap
            merged.extend(page[overlap:])
        balance = to_amount(merged[-1]["잔액"])

    return merged, {"order": order, "dropped": dropped, "gaps": gaps}
