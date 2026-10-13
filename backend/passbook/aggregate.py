"""월(月)별 합계 집계.

입금/지출/이자 레코드를 날짜순으로 훑으며, current_* 누적 변수에 더하다가
월이 바뀌는 순간 딕셔너리에 flush 한다.

반환 형식:
  {"MM": [총입금, 총지출, 총이자], ...}
  예) {"03": [849000, 0, 0], "05": [0, 218700, 0], "06": [856800, 91800, 21]}
"""


def _timeline(입금, 지출, 이자):
    """(날짜, 종류, 금액) 통합 타임라인을 날짜순으로 만든다."""
    rows = []
    for rec in 입금:
        for date, v in rec.items():
            rows.append((date, "입금", v[2]))   # 입금 레코드는 금액이 3번째
    for rec in 지출:
        for date, v in rec.items():
            rows.append((date, "지출", v[1]))   # 지출 레코드는 금액이 2번째
    for rec in 이자:
        for date, v in rec.items():
            rows.append((date, "이자", v[2]))
    rows.sort(key=lambda x: x[0])              # 'YYYYMMDD' 문자열은 그대로 정렬 가능
    return rows


def monthly_totals(입금, 지출, 이자):
    monthly = {}
    current_month = None
    current_입금 = current_지출 = current_이자 = 0

    for date, kind, amount in _timeline(입금, 지출, 이자):
        month = date[4:6]                      # '20260530' -> '05'

        if current_month is None:
            current_month = month

        if month != current_month:             # 월이 바뀜 -> 지금까지 합계를 flush
            monthly[current_month] = [current_입금, current_지출, current_이자]
            current_month = month
            current_입금 = current_지출 = current_이자 = 0

        if kind == "입금":
            current_입금 += amount
        elif kind == "지출":
            current_지출 += amount
        else:
            current_이자 += amount

    if current_month is not None:              # 마지막 달 flush
        monthly[current_month] = [current_입금, current_지출, current_이자]

    return monthly
