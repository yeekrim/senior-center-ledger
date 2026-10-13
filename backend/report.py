"""OCR 텍스트 줄 -> 파싱 -> 잔액 연쇄검증 -> 분류 -> 월별 집계 -> 출력.

run.py(고정 fixture)와 run_ocr.py(클라우드 OCR)가 공유하는 리포트 로직이다.

파싱과 보고를 나눠 둔다. 한 장짜리(또는 mock)는 print_report(lines)로 충분하고,
여러 장을 이어 붙인 경우(pages.merge_pages)는 이미 rows로 합쳐 두었으므로
print_report_rows(rows, merge_report)로 병합 결과까지 함께 보여준다.
"""

from passbook.aggregate import monthly_totals
from passbook.lines import parse_lines
from passbook.parse import classify_rows
from passbook.verify import verify_balance_chain


def _print_merge_report(merge_report):
    """여러 장을 이어 붙인 결과(순서·중복제거·끊김)를 보여준다."""
    order = merge_report["order"]
    print(f"=== 페이지 병합: {len(order)}장 → 잔액 순서 {order} ===")
    if merge_report["dropped"]:
        print(f"   겹쳐 찍힌 중복 {merge_report['dropped']}행 제거")
    for gap in merge_report["gaps"]:
        print(f"   ⚠ 이음새 끊김 (페이지 {gap['앞페이지']}→{gap['뒤페이지']}): "
              f"기대 시작잔액 {gap['기대시작잔액']:,} vs 실제 {gap['실제시작잔액']:,} "
              "— 사이에 빠진 페이지가 있는지 확인하세요")
    if not merge_report["gaps"]:
        print("   모든 이음새가 잔액으로 이어짐 ✓")


def print_report_rows(rows, merge_report=None, opening_balance=0):
    """이미 파싱된 rows에 대해 검증·분류·집계를 출력한다.

    merge_report: pages.merge_pages가 돌려준 병합 리포트. 주면 병합 결과도 보여준다.
    """
    if merge_report is not None:
        _print_merge_report(merge_report)

    print(f"=== 거래 {len(rows)}건 ===")

    result = verify_balance_chain(rows, opening_balance=opening_balance)
    if result["ok"]:
        print(f"=== 잔액 연쇄검증: {result['checked']}건 모두 일치 ✓ ===")
    else:
        print(f"=== 잔액 연쇄검증: 오류 {len(result['errors'])}건 ===")
        for e in result["errors"]:
            print(f"   [{e['date']} {e['사용내역']}] "
                  f"기대 {e['기대잔액']:,} vs 실제 {e['실제잔액']:,} (차이 {e['차이']:+,})")

    입금, 지출, 이자 = classify_rows(rows)

    print("\n=== 입금 (사용내역, 금액 순) ===")
    for rec in 입금:
        print("  ", rec)

    print("\n=== 지출 (금액, 사용내역 순) ===")
    for rec in 지출:
        print("  ", rec)

    print("\n=== 이자 (결산이자 별도) ===")
    for rec in 이자:
        print("  ", rec)

    print("\n=== 월별 합계  {월: [총입금, 총지출, 총이자]} ===")
    monthly = monthly_totals(입금, 지출, 이자)
    for month in sorted(monthly):
        입금액, 지출액, 이자액 = monthly[month]
        print(f"   {month}월 → 입금 {입금액:,} / 지출 {지출액:,} / 이자 {이자액:,}")


def print_report(lines, opening_balance=0):
    """OCR 줄 목록(한 장 또는 mock)을 파싱해 보고한다."""
    rows = parse_lines(lines)
    print(f"=== 파싱: {len(lines)}줄 중 거래 {len(rows)}건 인식 ===")
    print_report_rows(rows, opening_balance=opening_balance)
