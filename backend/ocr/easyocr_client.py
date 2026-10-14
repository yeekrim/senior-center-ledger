"""로컬 EasyOCR 엔진 어댑터.

이미지가 이 기기를 떠나지 않는다 — 금융정보 외부 미전송. 첫 실행 시 한국어 인식 모델(~100MB)을 ~/.EasyOCR 에 내려받는 것
외에는 네트워크를 쓰지 않는다.

반환 형식은 images[0].fields[].inferText / boundingPoly 로 맞춘다.
reconstruct.fields_to_lines()가 이 형식을 받으므로, 파싱 계층은 어느 엔진이
읽었는지(easyocr / mock) 알 필요가 없다.
"""

_reader = None  # 모델 로딩이 느려서(수 초) 프로세스당 한 번만 만든다


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
    return _reader


def call_easyocr(image_bytes: bytes) -> dict:
    """이미지 바이트를 로컬 EasyOCR로 인식해 fields/boundingPoly 형식 dict로 반환한다."""
    results = _get_reader().readtext(image_bytes)

    fields = []
    for bbox, text, _confidence in results:
        fields.append({
            "inferText": text,
            "boundingPoly": {"vertices": [
                {"x": float(x), "y": float(y)} for x, y in bbox
            ]},
        })
    return {"images": [{"fields": fields}]}
