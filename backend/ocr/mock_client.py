"""이미지를 읽지 않는 데모·테스트용 OCR 엔진.

EasyOCR 어댑터와 같은 응답 형식(images[0].fields[].inferText / boundingPoly)으로
fixture 텍스트를 돌려준다. 모델 없이 파이프라인 전체(암호화 -> 복호화 -> 인식 ->
줄 복원 -> 파싱)를 확인할 때 쓴다.
"""


def call_mock_ocr(image_bytes: bytes, gpu: bool = False) -> dict:
    """실제 이미지 바이트는 읽지 않고, fixture 줄을 토큰 단위 필드와 좌표로 재구성해 돌려준다."""
    from data.sample_lines import SAMPLE_LINES

    fields = []
    y = 0
    for line in SAMPLE_LINES:
        x = 0
        for token in line.split():
            fields.append({
                "inferText": token,
                "boundingPoly": {"vertices": [
                    {"x": x, "y": y}, {"x": x + 50, "y": y},
                    {"x": x + 50, "y": y + 20}, {"x": x, "y": y + 20},
                ]},
            })
            x += 60
        y += 30
    return {"images": [{"fields": fields}]}
