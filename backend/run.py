"""데모 실행: OCR 줄 텍스트 -> 파싱 -> 잔액 연쇄검증 -> 분류 -> 월별 집계.

실행:  python3 run.py   (backend 폴더 안에서)
"""

from data.sample_lines import SAMPLE_LINES
from report import print_report


def main():
    print_report(SAMPLE_LINES)


if __name__ == "__main__":
    main()
