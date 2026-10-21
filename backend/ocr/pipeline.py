"""이미지 -> OCR 엔진 -> 텍스트 줄.

사진은 OCR 호출이 끝날 때까지 이 함수의 지역 변수로만 잠깐 존재한다. 디스크에 쓰지 않고,
로그에도 남기지 않으며, OCR 응답을 받으면 즉시 참조를 버린다(finally 블록).

엔진:
  - easyocr (기본): 로컬 추론. 사진이 이 기기를 떠나지 않는다 — 외부 전송 구간 없음.
  - mock: 이미지를 읽지 않는 데모·테스트용.
"""

import time

from .denoise import normalize_lines
from .easyocr_client import call_easyocr
from .mock_client import call_mock_ocr
from .preprocess import crop_document, shrink
from .reconstruct import fields_to_lines
from settings import GPU_SIZES

ENGINES = {
    "easyocr": call_easyocr,
    "mock": call_mock_ocr,
}


# 실제로 이미지를 읽는 엔진. mock은 이미지를 보지 않으므로 줄이지 않는다.
READS_IMAGE = {"easyocr"}


def run_ocr_pipeline(image_bytes: bytes, engine: str = "easyocr",
                     preprocess: bool = False, denoise: bool = True,
                     long_side: int | None = None, timings: dict | None = None) -> list:
    """long_side: 주면 OCR 전에 긴 변을 이 크기로 줄인다(ocr.preprocess.shrink). None이면 원본.
    timings: dict를 주면 단계별 걸린 초를 채워 넣는다(축소 · OCR · 줄복원).

    preprocess(통장 영역 잘라내기)는 기본으로 끈다.

    실통장 사진 1장으로 측정했을 때 잘라낸 쪽이 오히려 나빴다(거래 18건 -> 16건).
    글자가 커지면 인식이 좋아질 것이라는 예상과 반대라서, 근거 없이 켜두지 않는다.
    사진이 더 모이면 다시 측정해서 판단한다.
    """
    if engine not in ENGINES:
        raise ValueError(f"지원하지 않는 엔진: {engine} (가능: {', '.join(ENGINES)})")

    timings = {} if timings is None else timings
    clock = time.perf_counter
    plaintext = image_bytes
    try:
        # 1) 전처리: 통장 영역만 잘라낸다(메모리 안에서만, 디스크 기록 없음).
        if preprocess and plaintext:
            plaintext = crop_document(plaintext)
        if long_side and plaintext and engine in READS_IMAGE:
            started = clock()
            plaintext = shrink(plaintext, long_side)
            timings["축소"] = clock() - started
        # 2) OCR 인식 (이 기기 안에서만)
        started = clock()
        # 큰 크기만 GPU로 읽는다. 실사진 6장을 원본으로 읽으면 CPU와 줄 텍스트가 똑같았고, 다시 읽는 사진은
        # 38초 -> 12초였다(6장을 연달아 원본으로 읽으면 30~40%). 1400px는 사진 1장 측정에서 GPU가 더 느렸다.
        ocr_response = ENGINES[engine](plaintext, gpu=long_side in GPU_SIZES)
        timings["OCR"] = clock() - started
    finally:
        # 3) 사진 즉시 폐기(디스크 기록 없음, 참조만 제거).
        plaintext = None

    started = clock()
    lines = fields_to_lines(ocr_response)
    lines = normalize_lines(lines) if denoise else lines
    timings["줄복원"] = clock() - started
    return lines
