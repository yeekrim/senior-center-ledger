"""데모 실행: (봉투암호화) 이미지 -> 복호화 -> OCR -> 파싱 -> 검증 -> 분류 -> 집계.

실행:  python3 run_ocr.py <이미지경로...> [엔진]   (backend 폴더 안에서)

이미지를 여러 장 주면 각 장을 따로 OCR·파싱한 뒤 잔액을 근거로 이어 붙인다
(passbook.pages.merge_pages). 사진 순서는 아무래도 좋다 — 잔액이 순서를 정한다.

엔진: easyocr(기본, 로컬 — 금융정보 외부 미전송) | mock(이미지 없이 fixture 데모)

이미지 경로를 생략하면 mock으로 전체 파이프라인(암호화 -> 복호화 -> 인식 -> 파싱)을
확인한다. 마지막 인자가 이미지 파일이 아니면 엔진 이름으로 본다.
"""

import os
import sys

from ocr.pipeline import run_ocr_pipeline
from passbook.lines import parse_lines
from passbook.pages import merge_pages
from report import print_report, print_report_rows

ENGINE_NAMES = {"easyocr", "mock"}


def _split_args(argv):
    """인자를 (이미지경로들, 엔진)으로 가른다. 마지막 인자가 파일이 아니고
    엔진 이름이면 엔진으로 떼어낸다."""
    args = list(argv)
    engine = None
    if args and args[-1] in ENGINE_NAMES and not os.path.exists(args[-1]):
        engine = args.pop()
    return args, engine


def main():
    image_paths, engine = _split_args(sys.argv[1:])
    engine = engine or ("easyocr" if image_paths else "mock")

    # 이미지 없음 -> mock 한 장으로 데모
    if not image_paths:
        print("(이미지 경로 미지정 -> mock 엔진으로 데모 진행)\n")
        lines = run_ocr_pipeline(b"", engine="mock")
        print(f"=== OCR(mock) 인식 결과: {len(lines)}줄 ===")
        for line in lines:
            print("  ", line)
        print()
        print_report(lines)
        return

    # 이미지 여러 장 -> 각 장을 OCR·파싱한 뒤 잔액으로 이어 붙인다
    pages = []
    for path in image_paths:
        with open(path, "rb") as f:
            image_bytes = f.read()
        lines = run_ocr_pipeline(image_bytes, engine=engine)
        rows = parse_lines(lines)
        print(f"=== {path}: OCR({engine}) {len(lines)}줄 → 거래 {len(rows)}건 ===")
        pages.append(rows)
    print()

    merged, merge_report = merge_pages(pages, opening_balance=0)
    print_report_rows(merged, merge_report=merge_report, opening_balance=0)


if __name__ == "__main__":
    main()
