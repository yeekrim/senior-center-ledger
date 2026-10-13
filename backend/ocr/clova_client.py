"""네이버 CLOVA OCR(General) API 클라이언트.

call_clova_ocr()이 호출되는 순간이 곧 '평문 이미지가 우리 인프라를 떠나
네이버 클라우드로 전송되는' 그 지점이다. 이 구간은 TLS로만 보호되며,
그 이상은 CLOVA 측의 데이터 정책(요청 이미지/결과 비저장)에 의존한다.

API 키가 없는 개발/데모 환경에서는 call_mock_ocr()이 동일한 응답 형식
(images[0].fields[].inferText / boundingPoly)을 흉내내 파이프라인 전체를
연결해서 확인할 수 있게 한다.
"""

import base64
import json
import os
import time
import uuid

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

CLOVA_SECRET_KEY = os.environ.get("CLOVA_OCR_SECRET_KEY")
CLOVA_INVOKE_URL = os.environ.get("CLOVA_OCR_INVOKE_URL")


class CloudOcrError(RuntimeError):
    pass


def call_clova_ocr(image_bytes: bytes) -> dict:
    """이미지 바이트를 CLOVA OCR General API로 전송하고 원시 JSON 응답을 반환한다."""
    if not (CLOVA_SECRET_KEY and CLOVA_INVOKE_URL):
        raise CloudOcrError(
            "CLOVA_OCR_SECRET_KEY / CLOVA_OCR_INVOKE_URL 환경변수가 설정되어 있지 않습니다."
        )
    if requests is None:  # pragma: no cover
        raise CloudOcrError("requests 패키지가 설치되어 있지 않습니다.")

    payload = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [{
            "format": "jpg",
            "name": "passbook",
            "data": base64.b64encode(image_bytes).decode("ascii"),
        }],
    }
    response = requests.post(
        CLOVA_INVOKE_URL,
        headers={"X-OCR-SECRET": CLOVA_SECRET_KEY, "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def call_mock_ocr(image_bytes: bytes) -> dict:
    """CLOVA 응답 형식을 흉내낸 mock. API 키 없이 파이프라인을 데모할 때 쓴다.

    실제 이미지 바이트는 읽지 않는다 — 여기서는 fixture 텍스트를 CLOVA가
    반환하는 필드/좌표 형식으로 재구성해 돌려줄 뿐이다.
    """
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
