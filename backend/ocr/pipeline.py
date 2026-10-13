"""이미지 -> (클라이언트 봉투암호화) -> (백엔드 복호화) -> OCR 엔진 -> 텍스트 줄.

평문 이미지는 decrypt_envelope()가 반환한 순간부터 OCR 호출이 끝날 때까지,
이 함수의 지역 변수로만 잠깐 존재한다. 디스크에 쓰지 않고, 로그에도 남기지
않으며, OCR 응답을 받으면 즉시 참조를 버린다(finally 블록).

엔진별 신뢰 경계:
  - easyocr (기본): 로컬 추론. 평문이 이 기기를 떠나지 않는다 — 외부 전송 구간 없음.
  - clova: call_clova_ocr() 호출 지점에서 평문이 우리 인프라를 떠나 벤더(네이버)
    클라우드로 전송된다. 그 구간은 TLS와 벤더의 데이터 정책으로만 보호된다.
  - mock: 이미지를 읽지 않는 데모용.
"""

from security.crypto import decrypt_envelope, encrypt_envelope, load_or_create_backend_keypair

from .clova_client import call_clova_ocr, call_mock_ocr
from .denoise import normalize_lines
from .easyocr_client import call_easyocr
from .preprocess import crop_document
from .reconstruct import fields_to_lines

ENGINES = {
    "easyocr": call_easyocr,
    "clova": call_clova_ocr,
    "mock": call_mock_ocr,
}


def client_side_encrypt(image_bytes: bytes, backend_public_key):
    """클라이언트가 촬영 직후 수행한다고 가정하는 암호화(데모에서는 같은 프로세스 안에서 흉내)."""
    return encrypt_envelope(image_bytes, backend_public_key)


def run_ocr_pipeline(image_bytes: bytes, engine: str = "easyocr",
                     preprocess: bool = False, denoise: bool = True) -> list:
    """preprocess(통장 영역 잘라내기)는 기본으로 끈다.

    실통장 사진 1장으로 측정했을 때 잘라낸 쪽이 오히려 나빴다(거래 18건 -> 16건).
    글자가 커지면 인식이 좋아질 것이라는 예상과 반대라서, 근거 없이 켜두지 않는다.
    사진이 더 모이면 다시 측정해서 판단한다.
    """
    if engine not in ENGINES:
        raise ValueError(f"지원하지 않는 엔진: {engine} (가능: {', '.join(ENGINES)})")

    private_key, public_key = load_or_create_backend_keypair()

    # 1) 클라이언트 -> 백엔드: 봉투 암호화. 이 함수 밖에서 image_bytes는 절대 평문으로 존재하지 않는다.
    envelope = client_side_encrypt(image_bytes, public_key)

    # 2) 백엔드 수신 & 복호화: 평문은 여기서부터 지역 변수로만 존재한다.
    plaintext = decrypt_envelope(envelope, private_key)
    try:
        # 3) 전처리: 통장 영역만 잘라낸다(메모리 안에서만, 디스크 기록 없음).
        if preprocess and plaintext:
            plaintext = crop_document(plaintext)
        # 4) OCR 인식 (clova일 때만 평문이 인프라를 떠난다 — 모듈 docstring 참조)
        ocr_response = ENGINES[engine](plaintext)
    finally:
        # 5) 평문 즉시 폐기(디스크 기록 없음, 참조만 제거).
        plaintext = None

    lines = fields_to_lines(ocr_response)
    return normalize_lines(lines) if denoise else lines
