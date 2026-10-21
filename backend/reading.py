"""통장 사진 한 장 -> 거래 행. 작게 빨리 읽고, 잔액이 안 맞을 때만 크게 다시 읽는다.

원본(4032px)을 그대로 OCR하면 CPU에서 사진 한 장에 70초 남짓 걸린다. 줄여서 읽으면
몇 배 빠르지만, 실제 통장 사진으로 재 보니 사진에 따라 거래를 놓치기도 했다.
그래서 두 단계로 읽는다:

  1) READ_SIZES의 첫 크기로 읽는다.
  2) 거래를 하나도 못 읽었거나, 이웃한 거래 사이의 잔액이 맞아떨어진 비율이
     RETRY_BELOW보다 낮으면 다음 크기로 다시 읽는다.
  3) 읽은 결과 중 '잔액이 맞아떨어진 이음매' 수가 가장 많은 쪽을 쓴다.
     같으면 연쇄 오류가 적은 쪽, 그다음 거래가 많은 쪽, 그다음 먼저 읽은(작은) 쪽.

오류 수만 보면 안 된다. 한 줄만 읽은 결과는 오류가 0이라 '깨끗해' 보이지만 거의 아무것도
읽지 못한 것이다. 실제 사진 6장으로 재 보니, 오류 수로 고르면 거래 6줄을 읽은 결과 대신
1줄을 읽은 결과를 골랐다. 반대로 오류가 하나라도 있으면 다시 읽게 하면, 6장 중 5장을
원본으로 다시 읽어(장당 1분 안팎) 느려지는데 나아진 건 1장뿐이었다.
RETRY_BELOW는 이 6장으로 정한 값이라, 사진이 더 모이면 다시 재서 조정한다.

잔액 연쇄는 페이지 안에서만 본다. 페이지 사이의 이음새는 pages.merge_pages가 따로 본다.

걸린 시간은 단계별로 로그에 남긴다. PAGE_BUDGET_SECONDS는 사진 한 장의 목표 시간으로,
넘으면 경고 로그를 남긴다. 목표를 정해 두고 재야 어디가 느려졌는지 알 수 있다. 목표값은
실제로 써 보면서 조정한다.
"""

import logging
import time

from ocr.pipeline import run_ocr_pipeline
from passbook.lines import parse_lines
from passbook.verify import verify_balance_chain
from settings import PAGE_BUDGET_SECONDS, READ_SIZES, RETRY_BELOW

# READ_SIZES(앞에서부터 시도할 OCR 크기, None은 원본), RETRY_BELOW, PAGE_BUDGET_SECONDS는
# settings.py에서 환경 변수로 바꿀 수 있다. 기본값은 위 docstring의 측정으로 정했다.

log = logging.getLogger("ledger")


def _chain_errors(rows) -> int:
    return len(verify_balance_chain(rows)["errors"]) if rows else 0


def _verified(rows, errors: int) -> int:
    """이웃한 거래 사이에서 잔액이 맞아떨어진 이음매 수."""
    return max(0, len(rows) - 1 - errors)


def _good_enough(rows, errors: int) -> bool:
    if not rows:
        return False
    joints = len(rows) - 1
    return joints == 0 or _verified(rows, errors) / joints >= RETRY_BELOW


def read_page(image_bytes: bytes, engine: str = "easyocr", sizes=READ_SIZES, name: str = "") -> dict:
    """사진 한 장을 읽어 {"rows", "크기", "시도", "시간"}을 돌려준다.

    시도: 크기별 {"크기", "행", "연쇄오류", "초"} 목록. 시간: 마지막으로 쓴 결과의 단계별 초와 합계.
    """
    started = time.perf_counter()
    attempts, best = [], None
    for size in sizes:
        timings = {}
        lines = run_ocr_pipeline(image_bytes, engine=engine, long_side=size, timings=timings)
        parse_started = time.perf_counter()
        rows = parse_lines(lines)
        timings["파싱"] = time.perf_counter() - parse_started

        errors = _chain_errors(rows)
        attempt = {"크기": size or "원본", "행": len(rows), "연쇄오류": errors,
                   "맞은이음매": _verified(rows, errors), "초": round(sum(timings.values()), 2)}
        attempts.append(attempt)
        rank = (_verified(rows, errors), -errors, len(rows))
        if best is None or rank > best[0]:          # 같으면 먼저 읽은(작은) 쪽을 그대로 둔다
            best = (rank, errors, rows, timings, attempt["크기"])
        if _good_enough(rows, errors):
            break

    _, errors, rows, timings, size = best
    total = time.perf_counter() - started
    log.info("사진 %s: %s · 행 %d · 연쇄오류 %d · %.1f초 (%s)", name or "-",
             " → ".join(f"{a['크기']}({a['초']}초)" for a in attempts), len(rows), errors, total,
             ", ".join(f"{k} {v:.1f}" for k, v in timings.items()))
    if total > PAGE_BUDGET_SECONDS:
        log.warning("사진 %s: 목표 %.0f초를 넘었습니다 (%.1f초)", name or "-", PAGE_BUDGET_SECONDS, total)

    return {"rows": rows, "크기": size, "시도": attempts,
            "시간": {**{k: round(v, 2) for k, v in timings.items()}, "합계": round(total, 2)}}
