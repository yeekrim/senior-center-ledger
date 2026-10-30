"""'사진 없이 둘러보기'에 쓰는 데모 검토 결과.

잡음 섞인 가상 통장 OCR 줄(noisy_ocr_lines)을 실제 사진과 같은 파싱 · 판정 경로로 돌린다.
GET /api/review가 이것을 돌려준다.
"""

from data.noisy_ocr_lines import NOISY_OCR_LINES
from ocr.denoise import normalize_lines
from passbook.lines import parse_lines
from passbook.review import review_transactions


def build_review():
    rows = parse_lines(normalize_lines(NOISY_OCR_LINES))
    review = review_transactions(rows, opening_balance=0)
    review["계좌"] = {"은행": "신협", "상품": "보통예탁금", "시작잔액": 0}
    return review
