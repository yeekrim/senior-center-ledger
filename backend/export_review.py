"""검토 화면(frontend/review.html)에 넣을 데이터를 만들어 주입한다.

실행:  python3 export_review.py   (backend 폴더 안에서)

아직 API 서버가 없어서 화면이 파일 하나로 열려야 한다. 그래서 review.html의
<script id="review-data"> 안에 결과 JSON을 직접 써 넣는다. FastAPI가 붙으면
이 스크립트는 사라지고 화면이 서버에서 같은 JSON을 받아오게 된다.
"""

import json
import re
from pathlib import Path

from data.real_ocr_lines import REAL_OCR_LINES
from ocr.denoise import normalize_lines
from passbook.lines import parse_lines
from passbook.review import review_transactions

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
DATA_TAG = re.compile(
    r'(<script id="review-data" type="application/json">).*?(</script>)', re.S)


def build_review():
    rows = parse_lines(normalize_lines(REAL_OCR_LINES))
    review = review_transactions(rows, opening_balance=0)
    review["계좌"] = {"은행": "신협", "상품": "보통예탁금", "시작잔액": 0}
    return review


def main():
    review = build_review()
    payload = json.dumps(review, ensure_ascii=False)

    (FRONTEND / "review-data.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    page = FRONTEND / "index.html"
    html = page.read_text(encoding="utf-8")
    updated, count = DATA_TAG.subn(lambda m: m.group(1) + payload + m.group(2), html)
    if count != 1:
        raise SystemExit("index.html에서 데이터 자리를 찾지 못했습니다.")
    page.write_text(updated, encoding="utf-8")

    print("주입 완료:", review["summary"])


if __name__ == "__main__":
    main()
